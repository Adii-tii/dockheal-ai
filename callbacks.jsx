function Callbacks() {
    function Download(cb) {
        console.log("Download starts")
        setTimeout(() => {
            console.log("Download ends");
            cb();
        }, 2000)
    }


    Download(function() {
        Compression(function() {
            Uploading (function(){
                console.log("All done");
            })
        })
    })
}