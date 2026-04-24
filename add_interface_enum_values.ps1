# ASTRA — Enum Value Additions for Interface Module
# ===================================================
# Run this from PowerShell in: C:\Users\Mason\Documents\ASTRA
#
# Adds new values to three Postgres enum types to match the expanded
# Python enums in backend/app/models/interface.py.
#
# Every statement uses IF NOT EXISTS and is idempotent —
# safe to run multiple times, safe to re-run after a partial failure.
#
# ORDER OF OPERATIONS:
#   1. FIRST: deploy the updated backend/app/models/interface.py
#      (otherwise the Python enum won't know about these values)
#   2. THEN: run this script to add them to Postgres
#   3. FINALLY: restart the backend container
#        docker compose restart backend
# ===================================================

$ErrorActionPreference = "Stop"

Write-Host "=== ConnectorType additions (10) ===" -ForegroundColor Cyan
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header_2_54mm';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header_2_00mm';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header_1_27mm';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header_idc';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'pcb_header_shrouded';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'jst_sh';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'jst_gh';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'jst_zh';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE connectortype ADD VALUE IF NOT EXISTS 'qwiic_stemma_qt';"

Write-Host ""
Write-Host "=== SignalType additions (~35) ===" -ForegroundColor Cyan

# Voltage-specific digital
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'digital_3v3';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'digital_5v';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'digital_12v';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'digital_lvds';"

# Specific analog
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'analog_voltage';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'analog_current_4_20ma';"

# Serial protocols
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'serial_rs232';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'serial_rs422';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'serial_rs485';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'serial_uart';"

# I2C
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'i2c_scl';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'i2c_sda';"

# SPI
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spi_clk';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spi_mosi';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spi_miso';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spi_cs';"

# CAN
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'can_high';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'can_low';"

# Aerospace buses (pin-level)
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'mil_std_1553_a';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'mil_std_1553_b';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'arinc_429';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'arinc_664';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spacewire_data';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'spacewire_strobe';"

# Ethernet (pin-level)
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'ethernet_100base_t';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'ethernet_1000base_t';"

# Media
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'video_analog';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'video_sdi';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'audio_analog';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'audio_digital_aes';"

# Fiber direction-specific
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'fiber_tx';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'fiber_rx';"

# Discrete command/status
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'discrete_command';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'discrete_status';"

# Ordnance
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'pyro_fire';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'pyro_arm';"

# Generic shield
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE signaltype ADD VALUE IF NOT EXISTS 'shield';"

Write-Host ""
Write-Host "=== PinDirection additions (3) ===" -ForegroundColor Cyan
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE pindirection ADD VALUE IF NOT EXISTS 'open_collector';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE pindirection ADD VALUE IF NOT EXISTS 'open_drain';"
docker exec astra-db-1 psql -U astra -d astra -c "ALTER TYPE pindirection ADD VALUE IF NOT EXISTS 'passive';"

Write-Host ""
Write-Host "=== Verification ===" -ForegroundColor Green
Write-Host "ConnectorType total values:" -ForegroundColor Yellow
docker exec astra-db-1 psql -U astra -d astra -c "SELECT COUNT(*) AS total FROM unnest(enum_range(NULL::connectortype)) AS t;"

Write-Host "SignalType total values:" -ForegroundColor Yellow
docker exec astra-db-1 psql -U astra -d astra -c "SELECT COUNT(*) AS total FROM unnest(enum_range(NULL::signaltype)) AS t;"

Write-Host "PinDirection total values:" -ForegroundColor Yellow
docker exec astra-db-1 psql -U astra -d astra -c "SELECT COUNT(*) AS total FROM unnest(enum_range(NULL::pindirection)) AS t;"

Write-Host ""
Write-Host "Done. Restart backend to pick up model changes: docker compose restart backend" -ForegroundColor Green
