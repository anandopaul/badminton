import { readFile } from 'node:fs/promises'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig, type Plugin } from 'vitest/config'

const profilePath = fileURLToPath(
  new URL('../output/player_profile.json', import.meta.url),
)
const chatApiTarget =
  process.env.RALLY_ATLAS_CHAT_API_TARGET ?? 'http://127.0.0.1:3001'

function localProfileDataPlugin(): Plugin {
  return {
    name: 'local-profile-data',
    apply: 'serve',
    configureServer(server) {
      server.middlewares.use((request, response, next) => {
        const pathname = request.url?.split('?')[0]
        if (pathname !== '/local-data/player_profile.json') {
          next()
          return
        }

        if (request.method !== 'GET' && request.method !== 'HEAD') {
          response.statusCode = 405
          response.setHeader('Allow', 'GET, HEAD')
          response.end()
          return
        }

        void readFile(profilePath)
          .then((contents) => {
            response.statusCode = 200
            response.setHeader('Content-Type', 'application/json; charset=utf-8')
            response.setHeader('Cache-Control', 'no-store')
            response.setHeader('X-Content-Type-Options', 'nosniff')
            response.setHeader('Content-Length', contents.length)
            response.end(request.method === 'HEAD' ? undefined : contents)
          })
          .catch((error: unknown) => {
            const code =
              typeof error === 'object' &&
              error !== null &&
              'code' in error &&
              typeof error.code === 'string'
                ? error.code
                : undefined

            if (code === 'ENOENT') {
              response.statusCode = 404
              response.setHeader('Content-Type', 'application/json; charset=utf-8')
              response.end(
                JSON.stringify({
                  error:
                    'Player profile data was not found. Run `python3 ../build_player_profiles.py` from the web directory.',
                }),
              )
              return
            }

            server.config.logger.error(
              `Unable to read local player profile data: ${
                error instanceof Error ? error.message : 'unknown filesystem error'
              }`,
            )
            response.statusCode = 500
            response.setHeader('Content-Type', 'application/json; charset=utf-8')
            response.end(JSON.stringify({ error: 'Unable to read local profile data.' }))
          })
      })
    },
  }
}

export default defineConfig({
  plugins: [react(), localProfileDataPlugin()],
  publicDir: false,
  server: {
    host: '127.0.0.1',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': {
        target: chatApiTarget,
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'node',
    setupFiles: './src/test/setup.ts',
    clearMocks: true,
    pool: 'vmThreads',
    maxWorkers: 1,
    fileParallelism: false,
  },
})
