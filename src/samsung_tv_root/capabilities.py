from __future__ import annotations

import json
import shlex
from enum import Enum
from typing import Any

from .config import TelevisionConfiguration
from .local_dimming import (
    LocalDimmingControlError,
    LocalDimmingModeStore,
    SamsungTvLocalDimmingControl,
    default_local_dimming_state_path,
)
from .root_agent import RootAgentConnection
from .source import (
    HdmiInput,
    Qn90bSourceControl,
    Qn90fSourceControl,
    SourceControlError,
)


QN90F_DISPLAY_CONTROL = (
    "/home/owner/share/tmp/sdk_tools/qn90f-probe/Qn90fDisplayControl.dll"
)


class CapabilityError(RuntimeError):
    pass


class CapabilityState(str, Enum):
    IMPLEMENTED = "implemented"
    PROVEN_NOT_PACKAGED = "proven_not_packaged"
    NOT_INVESTIGATED = "not_investigated"
    UNSUPPORTED = "unsupported"


SHARED_IMPLEMENTED_CAPABILITIES = (
    "root.acquire",
    "execute",
    "uep.status",
    "uep.disable",
    "source.list",
    "source.current",
    "source.select",
    "local_dimming.status",
    "local_dimming.set",
    "local_dimming.toggle",
    "remote.devices",
    "remote.observe",
    "remote.filter",
)

MODEL_ACTION_CAPABILITIES = {
    "qn90b": (),
    "qn90f": (
        "source.recover",
        "hdmi_policy.status",
        "hdmi_policy.enforce",
        "video_policy.status",
        "display.status",
        "display.picture_off",
        "display.wake",
    ),
}

SHARED_CAPABILITY_GAPS = {
    "volume.status": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native speaker-volume reads were validated, but this public adapter is not packaged here.",
    ),
    "volume.set": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native speaker-volume writes were validated, but this public adapter is not packaged here.",
    ),
    "volume.events": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native speaker-volume change events were validated, but this public adapter is not packaged here.",
    ),
    "events.tv_state": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Foreground app, source, lifecycle, and HDMI receiver events were validated, but this public adapter is not packaged here.",
    ),
}

QN90B_CAPABILITY_GAPS = {
    "source.recover": (
        CapabilityState.NOT_INVESTIGATED,
        "The QN90F HDMI presentation recovery operation has not been validated on QN90B.",
    ),
    "hdmi_policy.status": (
        CapabilityState.NOT_INVESTIGATED,
        "A QN90B PC, Game Mode, and Input Signal Plus adapter has not been implemented or validated.",
    ),
    "hdmi_policy.enforce": (
        CapabilityState.NOT_INVESTIGATED,
        "A QN90B PC, Game Mode, and Input Signal Plus adapter has not been implemented or validated.",
    ),
    "video_policy.status": (
        CapabilityState.NOT_INVESTIGATED,
        "The QN90B active video-policy interface has not been validated.",
    ),
    "display.status": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native QN90B display-state reads were validated in the operational controller, but this adapter is not packaged here.",
    ),
    "display.picture_off": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native QN90B Picture Off was validated in the operational controller, but this adapter is not packaged here.",
    ),
    "display.wake": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Native QN90B display wake was validated in the operational controller, but this adapter is not packaged here.",
    ),
    "screenshot.hdmi_960x540": (
        CapabilityState.NOT_INVESTIGATED,
        "This project has not validated the retained-analysis HDMI capture path on QN90B.",
    ),
    "overlay.graphics": (
        CapabilityState.NOT_INVESTIGATED,
        "This project has not validated transparent text or graphics overlays on QN90B.",
    ),
}

QN90F_CAPABILITY_GAPS = {
    "screenshot.hdmi_960x540": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Processed 960x540 HDMI capture was validated on QN90F, but this public adapter is not packaged here.",
    ),
    "overlay.graphics": (
        CapabilityState.PROVEN_NOT_PACKAGED,
        "Transparent text and graphics overlays were validated on QN90F, but this public adapter is not packaged here.",
    ),
}


class TelevisionCapabilities:
    def __init__(self, configuration: TelevisionConfiguration) -> None:
        self.configuration = configuration
        if configuration.model == "qn90f":
            self.source = Qn90fSourceControl()
        elif configuration.model == "qn90b":
            self.source = Qn90bSourceControl()
        else:
            raise CapabilityError(f"unsupported model: {configuration.model}")
        store = LocalDimmingModeStore(
            default_local_dimming_state_path(configuration.name)
        )
        self.local_dimming = SamsungTvLocalDimmingControl(store)

    def names(self) -> tuple[str, ...]:
        shared_actions = (
            "source.list",
            "source.current",
            "source.select",
            "local_dimming.status",
            "local_dimming.set",
            "local_dimming.toggle",
        )
        return shared_actions + MODEL_ACTION_CAPABILITIES[self.configuration.model]

    def inventory(self) -> list[dict[str, str]]:
        implemented_names = (
            SHARED_IMPLEMENTED_CAPABILITIES
            + MODEL_ACTION_CAPABILITIES[self.configuration.model]
        )
        implemented = [
            {"name": name, "state": CapabilityState.IMPLEMENTED.value}
            for name in implemented_names
        ]
        model_gaps = (
            QN90B_CAPABILITY_GAPS
            if self.configuration.model == "qn90b"
            else QN90F_CAPABILITY_GAPS
        )
        gaps = {**SHARED_CAPABILITY_GAPS, **model_gaps}
        return implemented + [
            {
                "name": name,
                "state": state.value,
                "detail": detail,
            }
            for name, (state, detail) in gaps.items()
        ]

    async def handle(
        self,
        connection: RootAgentConnection,
        action: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            return await self._handle(connection, action, request)
        except (SourceControlError, LocalDimmingControlError) as error:
            raise CapabilityError(str(error)) from error

    async def _handle(
        self,
        connection: RootAgentConnection,
        action: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        if action == "capabilities":
            return {"capabilities": self.inventory()}
        if action == "source.list":
            devices = await self.source.list_sources(connection)
            return {"sources": [device.to_dict() for device in devices]}
        if action == "source.current":
            current = await self.source.current_source(connection)
            return {"source": current.to_dict()}
        if action == "source.select":
            source = self._source(request)
            current = await self.source.current_source(connection)
            if current.source == source.value:
                return {
                    "changed": False,
                    "source": current.to_dict(),
                }
            selection = await self.source.select_source(connection, source)
            return {
                "changed": True,
                "selection": selection.to_dict(),
            }
        if action == "source.recover":
            self._require("source.recover")
            recovery = await self.source.recover_current_source(connection)
            return {"recovery": recovery.to_dict()}
        if action in {"hdmi_policy.status", "hdmi_policy.enforce"}:
            self._require(action)
            source = await self._requested_or_current_source(connection, request)
            activity_index = await self._activity_index(connection, source)
            if action == "hdmi_policy.status":
                policy = await self.source.hdmi_policy_status(
                    connection,
                    source,
                    activity_index,
                )
            else:
                policy = await self.source.enforce_pc_game_input_signal(
                    connection,
                    source,
                    activity_index,
                )
            return {"policy": policy.to_dict()}
        if action == "video_policy.status":
            self._require(action)
            video = await self.source.active_video_status(connection)
            return {"video_policy": video.to_dict()}
        if action.startswith("local_dimming."):
            return await self._local_dimming(connection, action, request)
        if action.startswith("display."):
            self._require(action)
            operation = {
                "display.status": "status",
                "display.picture_off": "pictureoff",
                "display.wake": "wake",
            }.get(action)
            if operation is None:
                raise CapabilityError(f"unknown display action: {action}")
            return {"display": await self._display(connection, operation)}
        raise CapabilityError(f"unknown capability action: {action}")

    async def _local_dimming(
        self,
        connection: RootAgentConnection,
        action: str,
        request: dict[str, Any],
    ) -> dict[str, Any]:
        source = await self.source.current_source(connection)
        expected = request.get("expected_source")
        if expected is not None:
            expected_source = HdmiInput.parse(
                self._required_string(expected, "expected_source")
            )
            if source.source != expected_source.value:
                raise CapabilityError(
                    f"current source is {source.source}, expected {expected_source.value}"
                )
        if action == "local_dimming.status":
            state = await self.local_dimming.status(connection, source)
            return {"local_dimming": state.to_dict()}
        if action == "local_dimming.toggle":
            change = await self.local_dimming.toggle(connection, source)
            return {"local_dimming": change.to_dict()}
        if action == "local_dimming.set":
            enabled = request.get("enabled")
            if not isinstance(enabled, bool):
                raise CapabilityError("local_dimming.set requires boolean enabled")
            change = await self.local_dimming.set_enabled(connection, source, enabled)
            return {"local_dimming": change.to_dict()}
        raise CapabilityError(f"unsupported local-dimming action: {action}")

    async def _requested_or_current_source(
        self,
        connection: RootAgentConnection,
        request: dict[str, Any],
    ) -> HdmiInput:
        value = request.get("source")
        if value is not None:
            return HdmiInput.parse(self._required_string(value, "source"))
        current = await self.source.current_source(connection)
        source = HdmiInput.from_source_type(current.source_type)
        if source is None:
            raise CapabilityError("current TV source is not HDMI")
        return source

    async def _activity_index(
        self,
        connection: RootAgentConnection,
        source: HdmiInput,
    ) -> int:
        devices = await self.source.list_sources(connection)
        matches = [
            device for device in devices if device.source_type == source.source_type
        ]
        if len(matches) != 1:
            raise CapabilityError(
                f"source list returned {len(matches)} entries for {source.value}"
            )
        index = matches[0].mbr_activity_index
        if index < 0:
            raise CapabilityError(f"{source.value} has no MBR activity index")
        return index

    async def _display(
        self,
        connection: RootAgentConnection,
        operation: str,
    ) -> dict[str, Any]:
        command = shlex.join(("/usr/bin/dotnet", QN90F_DISPLAY_CONTROL, operation))
        result = await connection.execute(command, 5.0)
        if result.timed_out:
            raise CapabilityError(f"display {operation} timed out")
        if result.exit_code != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise CapabilityError(
                f"display {operation} failed with exit {result.exit_code}"
                + (f": {detail}" if detail else "")
            )
        try:
            payload = json.loads(result.stdout)
        except json.JSONDecodeError as error:
            raise CapabilityError(
                f"display {operation} returned invalid JSON"
            ) from error
        if not isinstance(payload, dict):
            raise CapabilityError(f"display {operation} result is not an object")
        return payload

    def _require(self, action: str) -> None:
        if action not in self.names():
            model_gaps = (
                QN90B_CAPABILITY_GAPS
                if self.configuration.model == "qn90b"
                else QN90F_CAPABILITY_GAPS
            )
            state, detail = {**SHARED_CAPABILITY_GAPS, **model_gaps}.get(
                action,
                (
                    CapabilityState.NOT_INVESTIGATED,
                    f"No {self.configuration.model} adapter or validation record exists.",
                ),
            )
            raise CapabilityError(f"{action}: {state.value}: {detail}")

    @staticmethod
    def _source(request: dict[str, Any]) -> HdmiInput:
        return HdmiInput.parse(
            TelevisionCapabilities._required_string(request.get("source"), "source")
        )

    @staticmethod
    def _required_string(value: object, name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise CapabilityError(f"{name} must be a nonempty string")
        return value.strip()
