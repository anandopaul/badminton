// @vitest-environment jsdom

import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { profileFixture } from './test/profileFixture'

describe('Rally Atlas', () => {
  beforeEach(() => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => profileFixture,
      }),
    )
  })

  afterEach(() => {
    cleanup()
    vi.unstubAllGlobals()
  })

  it('searches aliases and compares players in their shared poule context', async () => {
    render(<App />)

    await screen.findByRole('heading', { name: 'Sample Ada' })
    fireEvent.click(screen.getByRole('button', { name: /add to compare/i }))

    const search = screen.getByRole('searchbox', {
      name: /search by name, alias, or player id/i,
    })
    fireEvent.change(search, { target: { value: 'a. example' } })
    expect(screen.getByRole('button', { name: /Sample Ada/ })).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /Sample Bo/ })).not.toBeInTheDocument()

    fireEvent.change(search, { target: { value: '' } })
    fireEvent.click(screen.getByRole('button', { name: /Sample Bo/ }))
    fireEvent.click(screen.getByRole('button', { name: /add to compare/i }))
    fireEvent.click(screen.getByRole('button', { name: /^compare/i }))

    expect(
      await screen.findByRole('heading', { name: 'Same poule, same season.' }),
    ).toBeInTheDocument()
    expect(screen.getByText(/Poule median win rate/i)).toBeInTheDocument()
    expect(screen.getByText(/not an official rank/i)).toBeInTheDocument()
  })
})
