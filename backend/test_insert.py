import sys
import os
import asyncio
import uuid
from datetime import datetime, timezone

sys.path.insert(0, r"c:\Users\Aditi Sable\DockHeal\backend")

from app.db.config.config import AsyncSessionLocal
from app.db.models import Container
from app.db.models.enums import ContainerStatus, HealthStatus

async def main():
    async with AsyncSessionLocal() as session:
        async with session.begin():
            c = Container(
                container_name="test-status-case",
                runtime_id=f"test_rt_{uuid.uuid4().hex[:12]}",
                image_name="nginx",
                status=ContainerStatus.RUNNING,
                health_status=HealthStatus.HEALTHY,
                last_seen=datetime.now(timezone.utc),
            )
            session.add(c)
            print("Adding container with enum objects...")
            await session.flush()
            print("Successfully flushed!")
            
            # Clean up
            await session.delete(c)

if __name__ == "__main__":
    asyncio.run(main())
