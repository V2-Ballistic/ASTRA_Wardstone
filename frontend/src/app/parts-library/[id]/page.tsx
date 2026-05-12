'use client';
import { useEffect, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { partsLibraryAPI } from '@/lib/parts-api';
import { formatApiError } from '@/lib/errors';
import type { LibraryPartResponse } from '@/lib/parts-types';
import {
  PART_STATUS_COLORS, PART_TYPE_COLORS, PART_TYPE_LABELS,
} from '@/lib/parts-types';

type Tab = 'overview' | 'dimensions' | 'material' | 'performance' | 'procurement';

interface FieldRowProps {
  label: string;
  value: string | number | boolean | null | undefined;
  unit?: string;
}

function FieldRow({ label, value, unit }: FieldRowProps) {
  const display =
    value === null || value === undefined || value === ''
      ? '—'
      : typeof value === 'boolean'
        ? (value ? 'Yes' : 'No')
        : String(value);
  return (
    <div className="flex justify-between py-1.5 border-b border-gray-100 dark:border-gray-800 last:border-0">
      <span className="text-xs text-gray-500 dark:text-gray-400">{label}</span>
      <span className="text-sm text-gray-900 dark:text-gray-100">
        {display}{display !== '—' && unit ? ` ${unit}` : ''}
      </span>
    </div>
  );
}

export default function PartDetailPage() {
  const params = useParams();
  const partId = Number(params?.id);
  const [part, setPart] = useState<LibraryPartResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<Tab>('overview');

  useEffect(() => {
    if (Number.isNaN(partId)) {
      setError('Invalid part id');
      setLoading(false);
      return;
    }
    setLoading(true);
    partsLibraryAPI
      .get(partId)
      .then((res) => {
        setPart(res.data);
        setError(null);
      })
      .catch((err) => {
        setError(formatApiError(err, 'Failed to load part'));
      })
      .finally(() => setLoading(false));
  }, [partId]);

  if (loading) return <div className="container mx-auto p-6 text-sm text-gray-500">Loading…</div>;
  if (error) return <div className="container mx-auto p-6 text-sm text-red-700">{error}</div>;
  if (!part) return null;

  return (
    <div className="container mx-auto p-6">
      <div className="mb-4">
        <Link href="/parts-library" className="text-xs text-blue-600 hover:underline">
          ← Parts Library
        </Link>
      </div>

      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span className={`text-xs px-2 py-0.5 rounded ${PART_TYPE_COLORS[part.part_type]}`}>
              {PART_TYPE_LABELS[part.part_type]}
            </span>
            <span className={`text-xs px-2 py-0.5 rounded ${PART_STATUS_COLORS[part.status]}`}>
              {part.status}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{part.name}</h1>
          <p className="font-mono text-sm text-gray-500 dark:text-gray-400 mt-1">
            {part.wardstone_part_number}
          </p>
          {part.description && (
            <p className="text-sm text-gray-600 dark:text-gray-300 mt-2">
              {part.description}
            </p>
          )}
        </div>
      </div>

      <div className="border-b border-gray-200 dark:border-gray-700 mb-4">
        <nav className="flex gap-1">
          {(['overview', 'dimensions', 'material', 'performance', 'procurement'] as Tab[]).map(
            (t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={
                  `px-4 py-2 text-sm capitalize ` +
                  (tab === t
                    ? 'border-b-2 border-blue-500 text-blue-600 dark:text-blue-400'
                    : 'text-gray-500 hover:text-gray-700 dark:hover:text-gray-300')
                }
              >
                {t}
              </button>
            ),
          )}
        </nav>
      </div>

      {tab === 'overview' && (
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-1">
            <FieldRow label="Manufacturer" value={part.manufacturer_name} />
            <FieldRow label="Manufacturer P/N" value={part.manufacturer_part_number} />
            <FieldRow label="CAGE Code" value={part.cage_code} />
            <FieldRow label="NSN" value={part.nsn} />
            <FieldRow label="Drawing Number" value={part.drawing_number} />
            <FieldRow label="Drawing Revision" value={part.drawing_revision} />
            <FieldRow label="Heritage" value={part.heritage} />
            <FieldRow label="Restricted Use" value={part.restricted_use} />
          </div>
          <div className="p-6 border border-dashed border-gray-300 dark:border-gray-700 rounded text-center text-sm text-gray-500">
            {part.step_file_id
              ? '3D preview available after Phase 4 (pythonOCC tessellation).'
              : 'No STEP file uploaded for this part.'}
          </div>
        </div>
      )}

      {tab === 'dimensions' && (
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-1">
            <FieldRow label="Bounding Box X" value={part.bounding_box_x_mm} unit="mm" />
            <FieldRow label="Bounding Box Y" value={part.bounding_box_y_mm} unit="mm" />
            <FieldRow label="Bounding Box Z" value={part.bounding_box_z_mm} unit="mm" />
            <FieldRow label="Volume" value={part.volume_mm3} unit="mm³" />
            <FieldRow label="Surface Area" value={part.surface_area_mm2} unit="mm²" />
          </div>
          <div className="space-y-1">
            <FieldRow label="Thread Size" value={part.thread_size} />
            <FieldRow label="Thread Standard" value={part.thread_standard} />
            <FieldRow label="Nominal Diameter" value={part.nominal_diameter_mm} unit="mm" />
            <FieldRow label="Nominal Length" value={part.nominal_length_mm} unit="mm" />
            <FieldRow label="Head Type" value={part.head_type} />
            <FieldRow label="Drive Type" value={part.drive_type} />
          </div>
          <div className="space-y-1">
            <FieldRow label="Hole Pattern Count" value={part.hole_pattern_count} />
            <FieldRow label="Hole Pattern Dia." value={part.hole_pattern_dia_mm} unit="mm" />
            <FieldRow label="Hole Pattern PCD" value={part.hole_pattern_pcd_mm} unit="mm" />
          </div>
        </div>
      )}

      {tab === 'material' && (
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-1">
            <FieldRow label="Material Name" value={part.material_name} />
            <FieldRow label="Material Standard" value={part.material_standard} />
            <FieldRow label="Material Class" value={part.material_class} />
            <FieldRow label="Density" value={part.density_g_cm3} unit="g/cm³" />
            <FieldRow label="Yield Strength" value={part.yield_strength_mpa} unit="MPa" />
            <FieldRow label="UTS" value={part.ultimate_strength_mpa} unit="MPa" />
            <FieldRow label="Elastic Modulus" value={part.elastic_modulus_gpa} unit="GPa" />
            <FieldRow label="Hardness" value={part.hardness} />
          </div>
          <div className="space-y-1">
            <FieldRow label="Thermal Conductivity" value={part.thermal_conductivity_wm} unit="W/m·K" />
            <FieldRow label="CTE" value={part.cte_um_m_c} unit="µm/m·°C" />
            <FieldRow label="Corrosion Protection" value={part.corrosion_protection} />
            <FieldRow label="Flammability Class" value={part.flammability_class} />
            <FieldRow label="Outgassing TML" value={part.outgassing_tml_pct} unit="%" />
            <FieldRow label="Outgassing CVCM" value={part.outgassing_cvcm_pct} unit="%" />
          </div>
        </div>
      )}

      {tab === 'performance' && (
        <div className="grid grid-cols-3 gap-6">
          <div className="space-y-1">
            <FieldRow label="Mass (nominal)" value={part.mass_nominal_g} unit="g" />
            <FieldRow label="Mass (max)" value={part.mass_max_g} unit="g" />
            <FieldRow label="Proof Load" value={part.proof_load_n} unit="N" />
            <FieldRow label="Clamp Load" value={part.clamp_load_n} unit="N" />
          </div>
          <div className="space-y-1">
            <FieldRow label="Torque (nominal)" value={part.torque_nominal_nm} unit="N·m" />
            <FieldRow label="Torque (min)" value={part.torque_min_nm} unit="N·m" />
            <FieldRow label="Torque (max)" value={part.torque_max_nm} unit="N·m" />
            <FieldRow label="Torque (lubricated)" value={part.torque_lubricated_nm} unit="N·m" />
            <FieldRow label="Locking Feature" value={part.locking_feature} />
            <FieldRow label="Safety Wire Holes" value={part.safety_wire_holes} />
          </div>
          <div className="space-y-1">
            <FieldRow label="Shear Strength" value={part.shear_strength_n} unit="N" />
            <FieldRow label="Bearing Load" value={part.bearing_load_n} unit="N" />
            <FieldRow label="Compression Set" value={part.compression_set_pct} unit="%" />
            <FieldRow label="Sealing Pressure (max)" value={part.sealing_pressure_max_bar} unit="bar" />
            <FieldRow label="Temp (min)" value={part.temperature_min_c} unit="°C" />
            <FieldRow label="Temp (max)" value={part.temperature_max_c} unit="°C" />
          </div>
        </div>
      )}

      {tab === 'procurement' && (
        <div className="grid grid-cols-2 gap-6">
          <div className="space-y-1">
            <FieldRow label="Unit Cost" value={part.unit_cost_usd} unit="USD" />
            <FieldRow label="Lead Time" value={part.lead_time_weeks} unit="weeks" />
            <FieldRow label="Min Order Qty" value={part.min_order_qty} />
            <FieldRow label="Preferred Supplier ID" value={part.preferred_supplier_id} />
            <FieldRow label="Supplier P/N" value={part.supplier_part_number} />
          </div>
          <div className="space-y-1">
            <FieldRow label="Qualification Status" value={part.qualification_status} />
            <FieldRow label="Qualification Basis" value={part.qualification_basis} />
            <FieldRow label="Shelf Life" value={part.shelf_life_months} unit="months" />
            <FieldRow label="Date of Manufacture" value={part.date_of_manufacture} />
            <FieldRow label="Restriction Notes" value={part.restriction_notes} />
          </div>
        </div>
      )}
    </div>
  );
}
