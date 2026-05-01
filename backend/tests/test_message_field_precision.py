"""
ASTRA — F-077 MessageField numeric precision
==============================================
File: backend/tests/test_message_field_precision.py

Verifies that scale_factor / offset / range columns survive a database
round-trip without binary-float rounding error. A common ICD scale
constant like 0.1 must come back as exactly 0.1, not as 0.1000000014…

The pre-fix model used Float (Postgres DOUBLE PRECISION). The 0021
migration switches the seven engineering-unit columns to NUMERIC(20, 9).

NB: SQLite is the test backend. SQLite represents NUMERIC as DECIMAL,
which is also exact for these values, so the test correctly exercises
the contract — values match exactly post-round-trip — even though the
underlying storage type differs from production Postgres.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models.interface import (
    System, Unit, BusDefinition, MessageDefinition, MessageField,
    BusProtocol, MessageDirection, FieldDataType,
)


@pytest.fixture()
def message(db_session, test_user, test_project):
    sys_ = System(
        system_id="SYS-PR", name="Precision Sys", system_type="subsystem",
        project_id=test_project.id, owner_id=test_user.id,
    )
    db_session.add(sys_)
    db_session.flush()

    unit = Unit(
        unit_id="UNIT-PR", project_id=test_project.id, system_id=sys_.id,
        name="Precision Unit", designation="PRC-001",
        part_number="PR-1", manufacturer="Test", unit_type="lru",
    )
    db_session.add(unit)
    db_session.flush()

    from app.models.interface import BusRole
    bus = BusDefinition(
        bus_def_id="BUS-PR", project_id=test_project.id, unit_id=unit.id,
        name="PrecBus", protocol=BusProtocol.MIL_STD_1553B,
        bus_role=BusRole.BUS_CONTROLLER,
    )
    db_session.add(bus)
    db_session.flush()

    msg = MessageDefinition(
        msg_def_id="MSG-PR", project_id=test_project.id,
        bus_def_id=bus.id, unit_id=unit.id, label="PrecMsg",
        direction=MessageDirection.TRANSMIT, word_count=1,
    )
    db_session.add(msg)
    db_session.commit()
    db_session.refresh(msg)
    return msg


def test_scale_factor_round_trip_preserves_decimal_exactly(db_session, message):
    f = MessageField(
        message_id=message.id,
        field_name="speed_mps",
        data_type=FieldDataType.UINT16,
        bit_length=16,
        scale_factor=Decimal("0.1"),
        offset_value=Decimal("0"),
        min_value=Decimal("0"),
        max_value=Decimal("6553.5"),
        resolution=Decimal("0.1"),
        accuracy=Decimal("0.05"),
    )
    db_session.add(f)
    db_session.commit()
    db_session.expire_all()

    fetched = db_session.query(MessageField).filter(MessageField.id == f.id).first()
    # The contract: scale_factor goes in as 0.1 and comes back as 0.1.
    # Pre-F-077 (Float) this would assert ~0.10000000149011612 != 0.1.
    assert Decimal(str(fetched.scale_factor)) == Decimal("0.1")
    assert Decimal(str(fetched.resolution)) == Decimal("0.1")
    assert Decimal(str(fetched.max_value)) == Decimal("6553.5")
    assert Decimal(str(fetched.accuracy)) == Decimal("0.05")


def test_high_precision_round_trip(db_session, message):
    # Nine-decimal-place value — the extreme of what NUMERIC(20, 9) holds.
    f = MessageField(
        message_id=message.id,
        field_name="position_rad",
        data_type=FieldDataType.INT32,
        bit_length=32,
        scale_factor=Decimal("0.000000001"),  # 1 nano-radian per LSB
        lsb_value=Decimal("0.000000001"),
    )
    db_session.add(f)
    db_session.commit()
    db_session.expire_all()

    fetched = db_session.query(MessageField).filter(MessageField.id == f.id).first()
    assert Decimal(str(fetched.scale_factor)) == Decimal("0.000000001")
    assert Decimal(str(fetched.lsb_value)) == Decimal("0.000000001")
