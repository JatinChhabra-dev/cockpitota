"""Virtual AAOS Cockpit Fleet Manager Package"""
from fleet.manager import app
from fleet.models import FleetInstance, InstanceStatus

__all__ = ["app", "FleetInstance", "InstanceStatus"]
