'use client';

/**
 * ASTRA — New Supplier Page
 * ===========================
 * File: frontend/src/app/catalog/suppliers/new/page.tsx
 *
 * Simple create-supplier form. On success, navigates to the new
 * supplier's detail page.
 *
 * Phase 3 — ASTRA-TDD-INTF-002.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChevronLeft, Building2, Loader2, Plus, AlertTriangle } from 'lucide-react';

import { catalogAPI } from '@/lib/catalog-api';
import { formatApiError } from '@/lib/errors';

export default function NewSupplierPage() {
  const router = useRouter();

  const [name, setName] = useState('');
  const [shortName, setShortName] = useState('');
  const [cageCode, setCageCode] = useState('');
  const [duns, setDuns] = useState('');
  const [website, setWebsite] = useState('');
  const [country, setCountry] = useState('');
  const [primaryContact, setPrimaryContact] = useState('');
  const [primaryEmail, setPrimaryEmail] = useState('');
  const [address, setAddress] = useState('');
  const [notes, setNotes] = useState('');
  const [isActive, setIsActive] = useState(true);

  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const canSave = name.trim().length > 0;

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      const r = await catalogAPI.createSupplier({
        name: name.trim(),
        short_name: shortName.trim() || undefined,
        cage_code: cageCode.trim() || undefined,
        duns: duns.trim() || undefined,
        website: website.trim() || undefined,
        country: country.trim() || undefined,
        primary_contact: primaryContact.trim() || undefined,
        primary_email: primaryEmail.trim() || undefined,
        address: address.trim() || undefined,
        notes: notes.trim() || undefined,
        is_active: isActive,
      });
      router.push(`/catalog/suppliers/${r.data.id}`);
    } catch (e: unknown) {
      setError(formatApiError(e, 'Failed to create supplier'));
      setSaving(false);
    }
  };

  return (
    <div>
      <button
        type="button"
        onClick={() => router.push('/catalog')}
        className="mb-4 flex items-center gap-1 text-xs text-slate-400 hover:text-blue-300"
      >
        <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" /> Back to Catalog
      </button>

      <h1 className="mb-1 text-xl font-bold text-slate-100 flex items-center gap-2">
        <Building2 className="h-5 w-5 text-blue-400" aria-hidden="true" />
        New Supplier
      </h1>
      <p className="mb-5 text-xs text-slate-500">
        Suppliers are global. Create once, reference from every project.
      </p>

      {error && (
        <div role="alert" className="mb-3 rounded-lg border border-red-500/20 bg-red-500/10 px-3 py-2 text-xs text-red-400 flex items-center gap-2">
          <AlertTriangle className="h-3.5 w-3.5" aria-hidden="true" /> {error}
        </div>
      )}

      <div className="max-w-3xl rounded-xl border border-astra-border bg-astra-surface p-5">
        <div className="grid grid-cols-2 gap-4">
          <div className="col-span-2">
            <Label htmlFor="sup-name" required>Name</Label>
            <Input id="sup-name" value={name} onChange={setName} placeholder="e.g. Honeywell Aerospace" />
          </div>
          <div>
            <Label htmlFor="sup-short">Short Name</Label>
            <Input id="sup-short" value={shortName} onChange={setShortName} placeholder="e.g. HW" />
          </div>
          <div>
            <Label htmlFor="sup-cage">CAGE Code</Label>
            <Input id="sup-cage" value={cageCode} onChange={setCageCode} placeholder="e.g. 55555" />
          </div>
          <div>
            <Label htmlFor="sup-duns">DUNS</Label>
            <Input id="sup-duns" value={duns} onChange={setDuns} placeholder="e.g. 005551234" />
          </div>
          <div>
            <Label htmlFor="sup-country">Country</Label>
            <Input id="sup-country" value={country} onChange={setCountry} placeholder="e.g. United States" />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sup-website">Website</Label>
            <Input id="sup-website" type="url" value={website} onChange={setWebsite} placeholder="https://example.com" />
          </div>
          <div>
            <Label htmlFor="sup-contact">Primary Contact</Label>
            <Input id="sup-contact" value={primaryContact} onChange={setPrimaryContact} placeholder="Jane Engineer" />
          </div>
          <div>
            <Label htmlFor="sup-email">Primary Email</Label>
            <Input id="sup-email" type="email" value={primaryEmail} onChange={setPrimaryEmail} placeholder="jane@example.com" />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sup-address">Address</Label>
            <textarea
              id="sup-address"
              value={address}
              onChange={(e) => setAddress(e.target.value)}
              rows={2}
              placeholder="Street, city, state, postal code"
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none"
            />
          </div>
          <div className="col-span-2">
            <Label htmlFor="sup-notes">Notes</Label>
            <textarea
              id="sup-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={3}
              placeholder="Optional context — preferred-vendor status, gotchas, etc."
              className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50 resize-none"
            />
          </div>
          <div className="col-span-2 flex items-center gap-2">
            <input
              id="sup-active"
              type="checkbox"
              checked={isActive}
              onChange={(e) => setIsActive(e.target.checked)}
              className="rounded border-astra-border bg-astra-bg"
            />
            <label htmlFor="sup-active" className="text-xs text-slate-300">Active (uncheck to mark deprecated)</label>
          </div>
        </div>

        <div className="mt-5 flex items-center justify-end gap-2 border-t border-astra-border pt-4">
          <button
            type="button"
            onClick={() => router.push('/catalog')}
            className="rounded-lg border border-astra-border px-4 py-2 text-xs text-slate-400 hover:text-slate-200"
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleSave}
            disabled={!canSave || saving}
            className="flex items-center gap-1.5 rounded-lg bg-blue-600 px-4 py-2 text-xs font-semibold text-white hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {saving ? <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden="true" /> : <Plus className="h-3.5 w-3.5" aria-hidden="true" />}
            Create Supplier
          </button>
        </div>
      </div>
    </div>
  );
}

// Local helpers — keep them at file bottom so the page reads top-down.

function Label({ htmlFor, children, required }: {
  htmlFor: string; children: React.ReactNode; required?: boolean;
}) {
  return (
    <label
      htmlFor={htmlFor}
      className="text-[10px] font-semibold uppercase tracking-wider text-slate-500 mb-1 block"
    >
      {children}{required && <span className="text-red-400 ml-0.5">*</span>}
    </label>
  );
}

function Input({ id, value, onChange, placeholder, type = 'text' }: {
  id: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  type?: string;
}) {
  return (
    <input
      id={id}
      type={type}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      className="w-full rounded-lg border border-astra-border bg-astra-bg px-3 py-2 text-sm text-slate-200 outline-none focus:border-blue-500/50"
    />
  );
}
