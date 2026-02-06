/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  experimental: {
    serverComponentsExternalPackages: ['snowflake-sdk'],
  },
  env: {
    SNOWFLAKE_DATABASE: 'DBAPI_REPLICA_DB',
    SNOWFLAKE_WAREHOUSE: 'COMPUTE_WH',
  },
}

module.exports = nextConfig
