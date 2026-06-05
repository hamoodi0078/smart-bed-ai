# ECE / Hardware Intern Contribution Guide: Danah AbuHalifa
## Designing and Testing the Physical Sensors, Circuits, and Power Systems

Welcome to the hardware and electronics team! As an Electrical / Electronics / ECE (Electrical & Computer Engineering) intern at Danah AbuHalifa, you will turn our smart bed concepts into physical reality. You will work with physical sensors, custom wiring, power systems, and embedded Linux.

---

## Role-Specific Tasks & Contributions

| Task Area | Why It Matters | Expected Skills | Expected Deliverables / Outcomes |
| :--- | :--- | :--- | :--- |
| **Raspberry Pi OS Setup** | The Raspberry Pi 5 is our bedside hub. It must boot up reliably, connect to local networks, and run Python sensor drivers automatically. | Linux terminal commands, writing systemd services, SSH, basic shell scripting. | A headless, secured Raspberry Pi 5 image that boots and starts the voice assistant and sensor bridges automatically on startup. |
| **Sensor Integration** | The bed relies on physical signals (pressure, temperature, heart rate). We need robust code to parse I2C, SPI, and GPIO data. | Python, GPIO libraries (gpiod/RPi.GPIO), I2C protocol, reading hardware datasheets. | Clean, non-blocking sensor driver classes (such as [pi_sensors.py](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/pi_sensors.py) and [pi_heart_rate.py](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/pi_heart_rate.py)) that publish sensor states in JSON format. |
| **LED Strip Wiring** | WS2812B NeoPixel strips require a 5V logic signal, but the Pi outputs 3.3V. Directly connecting them causes flickering or signal degradation. | Logic level shifters (74AHCT125), breadboarding, basic soldering, reading schematics. | A wired level-shifter circuit that converts the Pi's 3.3V GPIO signal to a clean 5V data stream for the 180 total LEDs. |
| **Power System Design** | A Pi 5, multiple sensors, and 180 LEDs draw high current (up to 5A-8A at peak). Poor power design causes system brownouts or electrical fire hazards. | Ohm's law, power calculation (Watts/Amps), selecting wire gauges, fusing, buck converters. | A documented power distribution schematic specifying power supply requirements, wire gauges, fuse ratings, and LED power injection points. |
| **Hardware Prototyping** | Before we install electronics inside a real bed, we must test everything on a desk. This avoids damaging expensive furniture or sensors. | Breadboarding, circuit layout, using bench power supplies and digital multimeters. | A fully functional "desktop prototype rig" containing the Pi 5, sensors, mini LED strips, and level shifters mounted on a test board. |
| **Hardware Debugging** | Electromagnetic interference, loose wires, and voltage drops can cause erratic sensor readings or audio noise. | Using logic analyzers, oscilloscopes, multimeters, and noise-isolation techniques. | Diagnostic guides showing stable voltage lines and noise-free I2C communication waveforms under maximum CPU and LED loads. |
| **PCB HAT Design** | Moving from a messy breadboard to a single custom circuit board (HAT) makes the system compact, neat, and highly reliable. | PCB design CAD tools (KiCad, EasyEDA, or Altium), component footprint matching, trace routing. | Schema designs and manufacturing Gerber files for a custom "Danah Bedside HAT" that slots directly onto the Pi's 40-pin GPIO header. |
| **Enclosure & Integration** | Exposed electronics pose safety hazards (liquids, static shock, dust). The Pi and level-shifting circuits need a protective, ventilated case. | 3D CAD modeling (Fusion 360, SolidWorks), 3D printing, understanding heat dissipation. | 3D-printable STL files for a ventilated enclosure that houses the Pi 5, bedside connectors, and has mounting points for sensor cables. |

---

## Onboarding Setup for ECE Interns

Follow these steps to get your hardware workbench ready for development:

1.  **Prepare the Tools:**
    *   Digital Multimeter (with continuity tester)
    *   Soldering Iron & Lead-free solder
    *   74AHCT125 logic level shifter IC
    *   Raspberry Pi 5 (with 5V/5A power supply)
2.  **Verify the Hardware Codebase:**
    *   Browse the existing Python drivers in [hardware/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/hardware/).
    *   Check [docs/raspberry-pi-setup.md](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/docs/raspberry-pi-setup.md) for pinout mapping and library prerequisites (such as `adafruit-circuitpython-neopixel` and system libraries).
3.  **Perform a Bench Test:**
    *   Assemble a basic circuit on a breadboard: connect a DHT22 temperature sensor and a single NeoPixel LED using the level shifter.
    *   Run `python main.py` or run individual test scripts under [tests/](file:///c:/Users/PC#####/Desktop/smart%20bed%20by%20me/tests/) (e.g. `test_pi_sensors.py`) to confirm that readings are parsed correctly.

---

## Safety & Prototyping Rules

When working on the Danah hardware systems, keep these safety practices in mind:
*   **No Hot-Wiring:** Always power off the main 5V power supply before plugging or unplugging wires on the Raspberry Pi GPIO pins.
*   **Double Check Polarities:** Reversing VCC (+5V) and GND (Ground) will instantly destroy the sensors or the Raspberry Pi. Always measure voltage polarities with your multimeter before connecting.
*   **Use Fuses:** Always include an inline fuse (typically 5A or 8A) on the main +5V line of the LED strips to prevent damage in case of a short circuit.
*   **Common Ground:** Ensure the Raspberry Pi ground pin, the external 5V power supply ground, and the LED strip ground are all connected together to form a common ground plane. Without this, logic signals will be unstable.
