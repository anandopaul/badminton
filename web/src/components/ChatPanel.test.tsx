// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import ChatPanel from './ChatPanel'

interface CapturedRequest {
  messages: Array<{ role: 'user' | 'assistant'; content: string }>
  context?: { selected_player_id?: number } | null
}

const requests: CapturedRequest[] = []

describe('ChatPanel', () => {
  beforeEach(() => {
    requests.length = 0
    let callNumber = 0
    vi.stubGlobal(
      'fetch',
      vi.fn().mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
        if (String(input) !== '/api/chat') {
          throw new Error(`Unexpected chat request URL: ${String(input)}`)
        }
        callNumber += 1
        requests.push(JSON.parse(String(init?.body)) as CapturedRequest)
        if (callNumber === 2) {
          return {
            ok: false,
            status: 503,
            json: async () => ({ detail: 'Ollama is unavailable for this test.' }),
          }
        }
        if (callNumber === 3) {
          return {
            ok: true,
            status: 200,
            json: async () => ({
              reply: 'Retry succeeded with the local profile data.',
              sources: ['output/2026/najaar_2026.json (poule 300)'],
            }),
          }
        }
        if (callNumber === 4) {
          throw new TypeError('Failed to fetch')
        }
        await new Promise((resolve) => setTimeout(resolve, 25))
        return {
          ok: true,
          status: 200,
          json: async () => ({
            reply: 'The local data shows a player history.',
            sources: ['output/player_profile.json'],
          }),
        }
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('keeps follow-up history, preserves failed messages for retry, and prevents duplicate sends', async () => {
    render(
      <ChatPanel
        selectedPlayerId={70001}
        selectedPlayerName="Sample Player"
      />,
    )
    const composer = screen.getByRole('textbox', { name: 'Message Rally Atlas' })
    const sendButton = screen.getByRole('button', { name: 'Send' })

    expect(sendButton).toBeDisabled()
    fireEvent.change(composer, { target: { value: 'Summarize this player.' } })
    fireEvent.click(sendButton)
    expect(sendButton).toBeDisabled()
    fireEvent.click(sendButton)
    expect(requests).toHaveLength(1)
    expect(
      await screen.findByText('The local data shows a player history.'),
    ).toBeInTheDocument()
    expect(requests[0]?.context?.selected_player_id).toBe(70001)

    fireEvent.change(composer, { target: { value: 'Which season was latest?' } })
    fireEvent.click(sendButton)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Ollama is unavailable for this test.',
    )
    expect(screen.getByText('Which season was latest?')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: 'Retry' }))
    expect(
      await screen.findByText('Retry succeeded with the local profile data.'),
    ).toBeInTheDocument()
    expect(requests[1]?.messages).toContainEqual({
      role: 'assistant',
      content: 'The local data shows a player history.',
    })
    expect(requests[2]?.messages).toContainEqual({
      role: 'user',
      content: 'Which season was latest?',
    })
    expect(screen.getByRole('button', { name: 'Send' })).toBeDisabled()

    fireEvent.change(composer, { target: { value: 'Could you repeat that?' } })
    fireEvent.click(screen.getByRole('button', { name: 'Send' }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Cannot reach the local chat API at /api/chat.',
    )
    expect(screen.getByText('Could you repeat that?')).toBeInTheDocument()
  })
})
