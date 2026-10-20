"""
cognicnc/services/mqtt_bridge.py
---------------------------------
Optional MQTT Industrial IoT publishing service.
Demonstrates standard Industry 4.0 messaging protocols (MQTT / JSON).

Graceful degradation:
  - If paho-mqtt is not installed, logs an INFO message and operates in dummy mode.
  - If the broker is unreachable (e.g., Mosquitto not running), logs a warning
    and does NOT crash the simulation or dashboard.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any, Dict, Optional

from cognicnc.logging_config import get_logger
from cognicnc.simulator.telemetry import TelemetrySample

logger = get_logger("mqtt_bridge")

# Check for paho-mqtt availability
_MQTT_AVAILABLE = False
try:
    import paho.mqtt.client as mqtt
    _MQTT_AVAILABLE = True
except ImportError:
    mqtt = None  # type: ignore


class MQTTBridge:
    """
    Industrial IoT MQTT Bridge for streaming telemetry and alerts.
    
    Topics:
      - Telemetry: cognicnc/telemetry/{machine_id}
      - Alerts:    cognicnc/alerts/{severity}
      - Heartbeat: cognicnc/heartbeat
    """

    def __init__(
        self,
        broker_host: str = "localhost",
        broker_port: int = 1883,
        client_id: str = "CogniCNC_Edge_Gateway",
        enabled: bool = False,
    ):
        self.broker_host = broker_host
        self.broker_port = broker_port
        self.client_id = client_id
        self.enabled = enabled and _MQTT_AVAILABLE
        self.client: Optional[Any] = None
        self.is_connected = False

        if enabled and not _MQTT_AVAILABLE:
            logger.info(
                "MQTT publishing requested but 'paho-mqtt' is not installed. "
                "Operating in simulation-only mode. (pip install paho-mqtt to enable)"
            )

        if self.enabled:
            self._connect()

    def _connect(self) -> None:
        """Attempt non-blocking connection to the MQTT broker."""
        try:
            self.client = mqtt.Client(
                client_id=self.client_id,
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,  # type: ignore
            )
            self.client.on_connect = self._on_connect
            self.client.on_disconnect = self._on_disconnect
            self.client.connect_async(self.broker_host, self.broker_port, keepalive=60)
            self.client.loop_start()
            logger.info(f"MQTT Bridge connecting to {self.broker_host}:{self.broker_port}...")
        except Exception as e:
            logger.warning(
                f"Could not initialize MQTT client: {e}. Running without live broker."
            )
            self.is_connected = False

    def _on_connect(self, client: Any, userdata: Any, flags: Any, reason_code: Any, properties: Any = None) -> None:
        if getattr(reason_code, "is_failure", False):
            logger.warning(f"MQTT connection failed with code: {reason_code}")
            self.is_connected = False
        else:
            self.is_connected = True
            logger.info(f"MQTT Bridge connected to broker at {self.broker_host}:{self.broker_port}")

    def _on_disconnect(self, client: Any, userdata: Any, disconnect_flags: Any, reason_code: Any, properties: Any = None) -> None:
        self.is_connected = False
        logger.debug(f"MQTT Bridge disconnected: {reason_code}")

    def publish_telemetry(self, sample: TelemetrySample) -> bool:
        """
        Publish machine telemetry to 'cognicnc/telemetry/{machine_id}'.
        Returns True if sent, False if bypassed or failed.
        """
        if not self.enabled or not self.is_connected or self.client is None:
            return False

        topic = f"cognicnc/telemetry/{sample.machine_id}"
        payload = json.dumps(sample.to_dict())

        try:
            res = self.client.publish(topic, payload, qos=0)
            return res.rc == 0
        except Exception as e:
            logger.debug(f"MQTT publish telemetry error: {e}")
            return False

    def publish_alert(self, alert_dict: Dict[str, Any]) -> bool:
        """
        Publish an alert to 'cognicnc/alerts/{severity}'.
        Returns True if sent, False if bypassed or failed.
        """
        if not self.enabled or not self.is_connected or self.client is None:
            return False

        severity = alert_dict.get("severity", "INFO").lower()
        topic = f"cognicnc/alerts/{severity}"
        payload = json.dumps(alert_dict)

        try:
            res = self.client.publish(topic, payload, qos=1)
            return res.rc == 0
        except Exception as e:
            logger.debug(f"MQTT publish alert error: {e}")
            return False

    def shutdown(self) -> None:
        """Cleanly disconnect and stop MQTT client loop."""
        if self.client is not None:
            try:
                self.client.loop_stop()
                self.client.disconnect()
                logger.info("MQTT Bridge disconnected cleanly.")
            except Exception as e:
                logger.debug(f"MQTT shutdown error: {e}")
            finally:
                self.is_connected = False