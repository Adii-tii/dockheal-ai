import sys
import os
import asyncio
import uuid
from datetime import datetime, timezone

sys.path.insert(0, r"c:\Users\Aditi Sable\DockHeal\backend")

# Database session & models
from app.db.config.config import AsyncSessionLocal
from app.db.models import Container, Investigation, LifecycleState, SeverityLevel, Notification
from app.db.models.enums import NotificationStatus
from app.db.dao.container_dao import ContainerDAO
from app.db.dao.notification_dao import NotificationDAO

# Centralized logger
from app.db.utils.event_logger import update_lifecycle, log_timeline_event

async def main():
    print("--- START VERIFICATION ---")
    container_id_2 = None
    container_id_3 = None
    
    # 1. Test Container DAO and Partial Index Uniqueness Lock
    async with AsyncSessionLocal() as session:
        async with session.begin():
            c_dao = ContainerDAO(session)
            # Create a test container
            c_id = f"test_runtime_{uuid.uuid4().hex[:12]}"
            container = await c_dao.upsert_by_runtime_id(
                runtime_id=c_id,
                container_name="test-uniqueness-container",
                image_name="nginx",
                status="running",
                health_status="healthy",
                labels={},
                ports=[],
                runtime_metadata={}
            )
            container_id = container.id
            print(f"[TEST 1] Upserted container with ID: {container_id}")

    # Start an active investigation for this container
    inv_id_1 = uuid.uuid4()
    async with AsyncSessionLocal() as session:
        async with session.begin():
            inv1 = Investigation(
                id=inv_id_1,
                container_id=container_id,
                title="Investigation 1",
                incident_summary="Test active lock",
                severity_level=SeverityLevel.P2,
                lifecycle_state=LifecycleState.DETECTED,
                started_at=datetime.now(timezone.utc),
                created_by="test_verify",
            )
            session.add(inv1)
            print(f"[TEST 1] Created first active investigation {inv_id_1}")

    # Attempt to start a second active investigation for the same container (should raise IntegrityError due to partial unique index)
    from sqlalchemy.exc import IntegrityError
    inv_id_2 = uuid.uuid4()
    try:
        async with AsyncSessionLocal() as session:
            async with session.begin():
                inv2 = Investigation(
                    id=inv_id_2,
                    container_id=container_id,
                    title="Investigation 2",
                    incident_summary="Test active lock duplicate",
                    severity_level=SeverityLevel.P2,
                    lifecycle_state=LifecycleState.DETECTED,
                    started_at=datetime.now(timezone.utc),
                    created_by="test_verify",
                )
                session.add(inv2)
        print("[FAIL] [TEST 1] Duplicate active investigation was allowed! Uniqueness check failed.")
    except IntegrityError:
        print("[SUCCESS] [TEST 1] DB-level partial unique index prevented duplicate active investigation.")

    # 2. Test Optimistic Locking (version mismatch)
    async with AsyncSessionLocal() as session:
        # Load the same investigation record into two different sessions
        inv_session1 = await session.get(Investigation, inv_id_1)
        
        async with AsyncSessionLocal() as session2:
            inv_session2 = await session2.get(Investigation, inv_id_1)
            
            # Modify via session 1
            inv_session1.lifecycle_state = LifecycleState.INVESTIGATING
            await session.commit()
            print("[TEST 2] Session 1 updated state to INVESTIGATING and committed.")
            
            # Modify via session 2 (should fail with StaleDataError or similar since version changed)
            from sqlalchemy.orm.exc import StaleDataError
            try:
                inv_session2.lifecycle_state = LifecycleState.RCA_IDENTIFIED
                await session2.commit()
                print("[FAIL] [TEST 2] Optimistic lock failed! Concurrent update allowed.")
            except StaleDataError:
                print("[SUCCESS] [TEST 2] StaleDataError raised successfully on concurrent version conflict.")
            except Exception as ex:
                print(f"[SUCCESS] [TEST 2] Conflicted update blocked with exception: {type(ex).__name__} - {ex}")

    # 3. Test Centralized Logger & Sequence Numbers
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Add some timeline events and check sequential sequence numbers
            await log_timeline_event(
                session=session,
                investigation_id=inv_id_1,
                event_type="TEST_EVENT_A",
                title="Event A",
                description="First timeline event",
                source_type="SYSTEM",
                severity="P3"
            )
            await log_timeline_event(
                session=session,
                investigation_id=inv_id_1,
                event_type="TEST_EVENT_B",
                title="Event B",
                description="Second timeline event",
                source_type="AI_AGENT",
                severity="P2"
            )
            print("[TEST 3] Logged timeline events Event A and Event B.")

    # Query them and verify sequence numbers
    from sqlalchemy import select
    from app.db.models import InvestigationTimelineEvent
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(InvestigationTimelineEvent)
            .where(InvestigationTimelineEvent.investigation_id == inv_id_1)
            .order_by(InvestigationTimelineEvent.sequence_number.asc())
        )
        events = res.scalars().all()
        for idx, event in enumerate(events):
            print(f"Event: sequence_number={event.sequence_number}, type={event.event_type}, title={event.title}")
        if len(events) >= 2 and events[0].sequence_number == 1 and events[1].sequence_number == 2:
            print("[SUCCESS] [TEST 3] Sequence numbers are sequential and unique.")
        else:
            print("[FAIL] [TEST 3] Sequence numbers check failed.")

    # 4. Test Notification Worker and Dead Lettering
    from app.ai.tools.registry import execute_tool
    print("[TEST 4] Dispatching alerts via execute_tool...")
    # This will trigger send_alert which saves a PENDING notification record in the DB
    execute_tool(
        tool_name="send_alert",
        parameters={
            "container_name": "test-uniqueness-container",
            "message": "Verify normal flow notification",
            "severity": "P2"
        },
        investigation_id=str(inv_id_1),
        actor="ai_test"
    )
    
    # This will trigger a notification containing "fail" which will trigger retry and then dead letter
    execute_tool(
        tool_name="send_alert",
        parameters={
            "container_name": "test-uniqueness-container",
            "message": "Trigger simulated fail connection error",
            "severity": "P1"
        },
        investigation_id=str(inv_id_1),
        actor="ai_test"
    )
    
    # Wait for the async task inside send_alert_tool to finish inserting records
    await asyncio.sleep(1.0)
    
    # Check pending notifications in DB
    async with AsyncSessionLocal() as session:
        ndao = NotificationDAO(session)
        pending = await ndao.get_pending()
        print(f"[TEST 4] Pending notifications in DB: {len(pending)}")
        for n in pending:
            print(f"Notification: id={n.id}, type={n.notification_type}, msg={n.metadata_.get('message')}")
            
    # Process them manually via process_pending_notifications to test notification worker logic
    from app.services.notification_worker import process_pending_notifications
    print("[TEST 4] Processing notifications first time...")
    processed = await process_pending_notifications()
    print(f"Processed {processed} notifications.")
    
    # Wait and process again to trigger retry backoff (the failed notification has backoff: 2**1 = 2 seconds)
    print("Waiting 3 seconds for retry backoff to expire...")
    await asyncio.sleep(3.0)
    print("[TEST 4] Processing notifications second time (retry 1)...")
    await process_pending_notifications()
    
    # Wait and process again to trigger retry 2 (backoff: 2**2 = 4 seconds)
    print("Waiting 5 seconds for retry backoff to expire...")
    await asyncio.sleep(5.0)
    print("[TEST 4] Processing notifications third time (retry 2 -> dead letter)...")
    await process_pending_notifications()
    
    # Verify that the failed notification is now marked as FAILED in DB
    async with AsyncSessionLocal() as session:
        ndao = NotificationDAO(session)
        failed = await ndao.get_failed()
        print(f"[TEST 4] Failed notifications in DB: {len(failed)}")
        for n in failed:
            print(f"Failed Notification: id={n.id}, msg={n.metadata_.get('message')}, status={n.status}, retries={n.metadata_.get('retry_count')}")
            
        sent = await ndao.get_by_status(NotificationStatus.SENT)
        print(f"[TEST 4] Sent notifications in DB: {len(sent)}")
        for n in sent:
            print(f"Sent Notification: id={n.id}, msg={n.metadata_.get('message')}, status={n.status}")
            
    # 5. Check Dead Letter Log File
    base_dir = os.path.dirname(os.path.abspath(__file__))
    dl_notif_path = os.path.join(base_dir, "logs", "dead_letter_notifications.log")
    if os.path.exists(dl_notif_path):
        print(f"[SUCCESS] [TEST 4] Dead letter log exists at {dl_notif_path}")
        with open(dl_notif_path, "r", encoding="utf-8") as f:
            print("Dead Letter Entry:", f.readline().strip())
    else:
        print("[FAIL] [TEST 4] Dead letter log was not created.")

    # 6. Test Failed Tool Execution Dead Lettering
    # Try calling a tool with illegal parameter to trigger a rejection/failure
    print("[TEST 6] Triggering failed tool execution...")
    execute_tool(
        tool_name="restart_container",
        parameters={
            "container_name": "test-uniqueness-container",
            "non_existent_param": "fail_me"
        },
        investigation_id=str(inv_id_1),
        actor="ai_test"
    )
    
    dl_tool_path = os.path.join(base_dir, "logs", "dead_letter_tools.log")
    if os.path.exists(dl_tool_path):
        print(f"[SUCCESS] [TEST 6] Tool dead letter log exists at {dl_tool_path}")
        with open(dl_tool_path, "r", encoding="utf-8") as f:
            print("Tool Dead Letter Entry:", f.readline().strip())
    else:
        print("[FAIL] [TEST 6] Tool dead letter log was not created.")
    # 7. Test Metrics Archival / Downsampling
    print("[TEST 7] Testing metrics archival and downsampling...")
    from app.db.models.system_metric import SystemMetric
    from app.db.models.system_metrics_hourly import SystemMetricHourly
    from app.db.dao.system_metric_dao import SystemMetricDAO
    from datetime import timedelta
    
    # Insert two metrics for our container that are 26 hours old (older than retention_hours=24)
    old_time = datetime.now(timezone.utc) - timedelta(hours=26)
    
    async with AsyncSessionLocal() as session:
        async with session.begin():
            m1 = SystemMetric(
                id=uuid.uuid4(),
                container_id=container_id,
                cpu_usage=10.0,
                memory_usage=20.0,
                disk_usage=30.0,
                network_usage=40.0,
                anomaly_score=0.5,
                created_at=old_time,
            )
            m2 = SystemMetric(
                id=uuid.uuid4(),
                container_id=container_id,
                cpu_usage=20.0,
                memory_usage=40.0,
                disk_usage=60.0,
                network_usage=80.0,
                anomaly_score=0.9,
                created_at=old_time + timedelta(minutes=15),
            )
            session.add_all([m1, m2])
            print("[TEST 7] Added old SystemMetric records to DB.")
            
    # Run the archiver
    async with AsyncSessionLocal() as session:
        async with session.begin():
            sm_dao = SystemMetricDAO(session)
            deleted_count = await sm_dao.archive_old_metrics(retention_hours=24)
            print(f"[TEST 7] Run archive_old_metrics. Deleted count = {deleted_count}")
            if deleted_count >= 2:
                print("[SUCCESS] [TEST 7] Old raw metrics were deleted successfully.")
            else:
                print(f"[FAIL] [TEST 7] Raw metrics deletion failed. Deleted: {deleted_count}")

    # Query system_metrics_hourly to verify the downsampled row
    async with AsyncSessionLocal() as session:
        res = await session.execute(
            select(SystemMetricHourly).where(SystemMetricHourly.container_id == container_id)
        )
        hourly_rows = res.scalars().all()
        print(f"[TEST 7] Found hourly aggregated rows: {len(hourly_rows)}")
        if hourly_rows:
            hr = hourly_rows[0]
            print(f"Hourly: cpu_avg={hr.cpu_usage_avg}, mem_avg={hr.memory_usage_avg}, disk_avg={hr.disk_usage_avg}, net_avg={hr.network_usage_avg}, anomaly_max={hr.anomaly_score_max}")
            # Verify values: avg(10,20)=15, avg(20,40)=30, avg(30,60)=45, avg(40,80)=60, max(0.5,0.9)=0.9
            if abs(hr.cpu_usage_avg - 15.0) < 0.1 and abs(hr.anomaly_score_max - 0.9) < 0.1:
                print("[SUCCESS] [TEST 7] Hourly aggregation calculation is correct.")
            else:
                print("[FAIL] [TEST 7] Hourly aggregation calculation is incorrect.")
        else:
            print("[FAIL] [TEST 7] Hourly aggregated row was not found.")

    # 8. Test Approval Timeout Transitions
    print("[TEST 8] Testing approval timeouts and lifecycle transitions...")
    from app.db.dao.investigation_dao import InvestigationDAO
    
    inv_id_p2 = uuid.uuid4() # P2 -> TIMED_OUT
    inv_id_p1 = uuid.uuid4() # P1 -> ESCALATED
    
    # Create two containers for the two investigations to satisfy partial index
    async with AsyncSessionLocal() as session:
        async with session.begin():
            c_dao = ContainerDAO(session)
            c_id_2 = f"test_runtime_{uuid.uuid4().hex[:12]}"
            c_id_3 = f"test_runtime_{uuid.uuid4().hex[:12]}"
            
            container_2 = await c_dao.upsert_by_runtime_id(
                runtime_id=c_id_2,
                container_name="test-uniqueness-container-2",
                image_name="nginx",
                status="running",
                health_status="healthy",
                labels={},
                ports=[],
                runtime_metadata={}
            )
            container_3 = await c_dao.upsert_by_runtime_id(
                runtime_id=c_id_3,
                container_name="test-uniqueness-container-3",
                image_name="nginx",
                status="running",
                health_status="healthy",
                labels={},
                ports=[],
                runtime_metadata={}
            )
            container_id_2 = container_2.id
            container_id_3 = container_3.id
            print(f"[TEST 8] Created containers with IDs: {container_id_2}, {container_id_3}")
            
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Awaiting approval, timeout has passed (e.g. 10 minutes ago)
            timeout_time = datetime.now(timezone.utc) - timedelta(minutes=10)
            
            inv_p2 = Investigation(
                id=inv_id_p2,
                container_id=container_id_2,
                title="P2 Investigation Timeout Test",
                incident_summary="Test low severity timeout",
                severity_level=SeverityLevel.P2,
                lifecycle_state=LifecycleState.AWAITING_APPROVAL,
                approval_timeout_at=timeout_time,
                started_at=datetime.now(timezone.utc),
                created_by="test_verify",
            )
            
            inv_p1 = Investigation(
                id=inv_id_p1,
                container_id=container_id_3,
                title="P1 Investigation Timeout Test",
                incident_summary="Test high severity timeout",
                severity_level=SeverityLevel.P1,
                lifecycle_state=LifecycleState.AWAITING_APPROVAL,
                approval_timeout_at=timeout_time,
                started_at=datetime.now(timezone.utc),
                created_by="test_verify",
            )
            session.add_all([inv_p2, inv_p1])
            print("[TEST 8] Created P2 and P1 investigations awaiting approval with expired timeouts.")
            
    # Polling timed out approvals via DAO
    async with AsyncSessionLocal() as session:
        async with session.begin():
            inv_dao = InvestigationDAO(session)
            timed_out = await inv_dao.get_timed_out_approvals()
            print(f"[TEST 8] Found timed out approvals: {len(timed_out)}")
            
            # Transition them based on severity
            for inv in timed_out:
                if inv.id not in (inv_id_p2, inv_id_p1):
                    continue
                is_high = inv.severity_level in (SeverityLevel.P0, SeverityLevel.P1)
                new_state = LifecycleState.ESCALATED if is_high else LifecycleState.TIMED_OUT
                
                await update_lifecycle(
                    session=session,
                    investigation_id=inv.id,
                    new_state=new_state
                )
                print(f"Transitioned investigation {inv.id} ({inv.severity_level}) to {new_state}")

    # Re-fetch and verify transitions in database
    async with AsyncSessionLocal() as session:
        async with session.begin():
            inv_dao = InvestigationDAO(session)
            refreshed_p2 = await inv_dao.get_by_id(inv_id_p2)
            refreshed_p1 = await inv_dao.get_by_id(inv_id_p1)
            
            print(f"Refreshed P2 state: {refreshed_p2.lifecycle_state}")
            print(f"Refreshed P1 state: {refreshed_p1.lifecycle_state}")
            
            if refreshed_p2.lifecycle_state == LifecycleState.TIMED_OUT and refreshed_p1.lifecycle_state == LifecycleState.ESCALATED:
                print("[SUCCESS] [TEST 8] Low severity transitioned to TIMED_OUT and high severity to ESCALATED.")
            else:
                print("[FAIL] [TEST 8] Timeout lifecycle transitions failed.")
                
    # Clean up test data
    print("[CLEANUP] Cleaning up test database records...")
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # Delete notifications
            await session.execute(
                sqlalchemy.text("DELETE FROM notifications WHERE investigation_id = :iid"),
                {"iid": inv_id_1}
            )
            # Delete timeline events
            await session.execute(
                sqlalchemy.text("DELETE FROM investigation_timeline_events WHERE investigation_id = :iid"),
                {"iid": inv_id_1}
            )
            # Delete investigations
            await session.execute(
                sqlalchemy.text("DELETE FROM investigations WHERE id IN (:iid, :iid_p2, :iid_p1)"),
                {"iid": inv_id_1, "iid_p2": inv_id_p2, "iid_p1": inv_id_p1}
            )
            # Delete hourly metrics
            await session.execute(
                sqlalchemy.text("DELETE FROM system_metrics_hourly WHERE container_id = :cid"),
                {"cid": container_id}
            )
            # Delete containers
            await session.execute(
                sqlalchemy.text("DELETE FROM containers WHERE id IN (:cid1, :cid2, :cid3)"),
                {"cid1": container_id, "cid2": container_id_2, "cid3": container_id_3}
            )
            
    print("--- VERIFICATION COMPLETE ---")

if __name__ == "__main__":
    import sqlalchemy
    asyncio.run(main())
