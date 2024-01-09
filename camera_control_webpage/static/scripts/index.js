var cameraVals = {}
var sliderInitVals = {}
document.onload = function() {
    fetch("/get_control_bounds", {
        method: "GET",
        headers: {
            "Accept": "application/json",
        },
    }).then(r => r.json())
    .then(r => {
        initControlSliders(r)
        setEventHandlers();
    });
}();

function initControlSliders(initVals) {
    sliderInitVals = initVals
    for (var sliderId in initVals) {
        sliderVals = initVals[sliderId];
        var slider = document.getElementById(sliderId);
        slider.min = sliderVals["min"];
        slider.max = sliderVals["max"];
        slider.default = sliderVals["default"];
        slider.value = sliderVals["value"];
        slider.step = sliderVals["step"];
        cameraVals[sliderId] = slider.value;
        document.getElementById(sliderId + "_value").value = sliderVals["value"];
    }
}

function setEventHandlers() {
    for (var sliderId in sliderInitVals) {
        var slider = document.getElementById(sliderId);
        slider.addEventListener("change", function() {
            var myId = this.id;
            cameraVals[myId] = this.value;
            document.getElementById(myId + "_value").value = this.value;
            fetch("/set_camera_control", {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(cameraVals),
            });
        });
        document.getElementById(sliderId + "_reset")
        .addEventListener("click", function() {
            var myId = this.id.replace("_reset", "");
            var slider = document.getElementById(myId);
            slider.value = sliderInitVals[myId].default;
            slider.dispatchEvent(new Event("change"));
        })
    }
}
