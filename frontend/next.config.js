/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // Permanent (308) redirects. Keep the SYSARCH-002 entries first;
  // CLEANUP-002 appended four /parts-library → /catalog rewrites in
  // Phase 3.
  async redirects() {
    return [
      // ── TDD-SYSARCH-002 §6.3: System / Unit detail pages relocated ──
      // from /interfaces/... to /system-architecture/... — old paths
      // 307-redirect (permanent: true) so existing bookmarks survive.
      // The :unitId(\\d+) constraint ensures the legacy numeric pattern
      // doesn't catch /interfaces/import, /interfaces/connect, etc.
      {
        source: '/projects/:id/interfaces/system/:systemId',
        destination: '/projects/:id/system-architecture/system/:systemId',
        permanent: true,
      },
      {
        source: '/projects/:id/interfaces/unit/:unitId',
        destination: '/projects/:id/system-architecture/unit/:unitId',
        permanent: true,
      },
      // Legacy variant (numeric only — see gotcha §8 in the prompt).
      {
        source: '/projects/:id/interfaces/:unitId(\\d+)',
        destination: '/projects/:id/system-architecture/unit/:unitId',
        permanent: true,
      },

      // ── CLEANUP-002 Phase 3: Parts Library → Catalog ──
      // The /parts-library module is superseded by Catalog Parts. The
      // sidebar entry is removed (Sidebar.tsx); the routes are kept
      // in place under frontend/src/app/parts-library/ but every
      // traffic path is rewritten here so existing bookmarks land on
      // the catalog equivalents. The legacy route tree is sunset by a
      // separate TDD.
      {
        source: '/parts-library',
        destination: '/catalog',
        permanent: true,
      },
      {
        source: '/parts-library/pending-imports',
        destination: '/catalog/pending-imports',
        permanent: true,
      },
      {
        source: '/parts-library/pending-imports/:id',
        destination: '/catalog/pending-imports/:id',
        permanent: true,
      },
      {
        source: '/parts-library/:id',
        destination: '/catalog/parts/:id',
        permanent: true,
      },
    ];
  },
};

module.exports = nextConfig;
