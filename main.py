from image_controller import ImageController
from led_controller import LEDInterface
from time import sleep

if __name__ == "__main__":
    with ImageController() as imageController, \
        LEDInterface() as ledInterface:
        try:
            imageController.set_led_interface(ledInterface)

            prevPower = False
            while True:
                power = ledInterface.update_and_get_power_state()
                if power and not prevPower:
                    imageController.start_capture_and_processing()
                    prevPower = power
                elif not power and prevPower:
                    imageController.stop_capture_and_processing()
                    prevPower = power
                else:
                    prevPower = power
                    sleep(0.3)
        except KeyboardInterrupt:
            pass
