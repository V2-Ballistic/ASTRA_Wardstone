"""F-013: extend interface enums via Alembic (replaces add_interface_enum_values.ps1)

Revision ID: 0009
Revises: 0008
Create Date: 2026-04-30

Migrates the 50 ALTER TYPE … ADD VALUE statements that previously
lived only in the ad-hoc PowerShell script
``add_interface_enum_values.ps1`` into a tracked Alembic revision
so a fresh `alembic upgrade head` produces an enum schema identical
to the post-script dev DB.

Coverage (post-0007 baseline):
  connectortype : 10 new values  (pcb_header* family + jst_sh/gh/zh + qwiic_stemma_qt)
  signaltype    : 37 new values  (digital_*, analog_*, serial_*, i2c_*, spi_*,
                                  can_*, mil_std_1553_*, arinc_*, spacewire_*,
                                  ethernet_*, video_*, audio_*, fiber_*,
                                  discrete_*, pyro_*, shield)
  pindirection  :  3 new values  (open_collector, open_drain, passive)

Each statement is wrapped in `IF NOT EXISTS` so re-runs on a DB that
already has the values (every dev DB that ran the .ps1) are no-ops.

Postgres forbids `ALTER TYPE … ADD VALUE` inside a transaction; the
migration runs the whole batch in autocommit mode.

Downgrade is a no-op. Postgres has no clean way to remove an enum
value: dropping it would break any row currently using that value
and there's no mass-rewrite-then-drop primitive. If a downgrade is
needed for a true rollback the recommended path is restore-from-backup
or a cascading data migration that rewrites affected rows first.
"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0009"
down_revision: Union[str, None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# ── Values to add, in the original .ps1 order so enum_range() output
#    matches the dev DB byte-for-byte after upgrade.
_CONNECTORTYPE_NEW = [
    "pcb_header", "pcb_header_2_54mm", "pcb_header_2_00mm",
    "pcb_header_1_27mm", "pcb_header_idc", "pcb_header_shrouded",
    "jst_sh", "jst_gh", "jst_zh", "qwiic_stemma_qt",
]

_SIGNALTYPE_NEW = [
    "digital_3v3", "digital_5v", "digital_12v", "digital_lvds",
    "analog_voltage", "analog_current_4_20ma",
    "serial_rs232", "serial_rs422", "serial_rs485", "serial_uart",
    "i2c_scl", "i2c_sda",
    "spi_clk", "spi_mosi", "spi_miso", "spi_cs",
    "can_high", "can_low",
    "mil_std_1553_a", "mil_std_1553_b",
    "arinc_429", "arinc_664",
    "spacewire_data", "spacewire_strobe",
    "ethernet_100base_t", "ethernet_1000base_t",
    "video_analog", "video_sdi",
    "audio_analog", "audio_digital_aes",
    "fiber_tx", "fiber_rx",
    "discrete_command", "discrete_status",
    "pyro_fire", "pyro_arm",
    "shield",
]

_PINDIRECTION_NEW = [
    "open_collector", "open_drain", "passive",
]


def upgrade() -> None:
    # ALTER TYPE ADD VALUE cannot run inside a transaction in Postgres.
    with op.get_context().autocommit_block():
        for v in _CONNECTORTYPE_NEW:
            op.execute(
                f"ALTER TYPE connectortype ADD VALUE IF NOT EXISTS '{v}';"
            )
        for v in _SIGNALTYPE_NEW:
            op.execute(
                f"ALTER TYPE signaltype ADD VALUE IF NOT EXISTS '{v}';"
            )
        for v in _PINDIRECTION_NEW:
            op.execute(
                f"ALTER TYPE pindirection ADD VALUE IF NOT EXISTS '{v}';"
            )


def downgrade() -> None:
    """Intentionally a no-op — see module docstring."""
    pass
