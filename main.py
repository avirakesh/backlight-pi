import user_pref
from image_controller import ImageController
from led_controller import LEDInterface

if __name__ == "__main__":
    with ImageController() as imageController, \
        LEDInterface() as ledInterface:
        try:
            imageController.set_led_interface(ledInterface)
            imageController.start_capture_and_processing()
        except KeyboardInterrupt:
            pass
