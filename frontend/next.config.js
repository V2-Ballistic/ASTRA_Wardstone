/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',

  // TDD-SYSARCH-002 §6.3: System / Unit Detail pages relocated from
  // /interfaces/... to /system-architecture/... — old paths
  // 307-redirect (permanent: true) so existing bookmarks survive.
  // The :unitId(\\d+) constraint ensures the legacy numeric pattern
  // doesn't catch /interfaces/import, /interfaces/connect, etc.
  async redirects() {
    return [
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
    ];
  },
};

module.exports = nextConfig;
