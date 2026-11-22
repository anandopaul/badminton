import { describe, expect, it } from 'vitest'
import { parseProfileData } from './profileData'
import {
  appearancesForPlayer,
  commonPouleContexts,
  filterPlayers,
  latestAppearance,
  profileCoverage,
} from './selectors'
import { profileFixture } from '../test/profileFixture'

describe('parseProfileData', () => {
  it('validates the profile schema and resolves normalized catalogs', () => {
    const index = parseProfileData(profileFixture)

    expect(index.document.players).toHaveLength(3)
    expect(index.seasonsById.get('najaar_2026')?.year).toBe(2026)
    expect(index.groupsById.get('senioren')?.name).toBe('Senioren')
    expect(index.teamsById.get(21)?.name).toBe('Sample Seniors 2')
  })

  it('rejects invalid schema data with actionable validation details', () => {
    const invalid = { ...profileFixture, schema_version: '1.0' }

    expect(() => parseProfileData(invalid)).toThrow(
      'does not match the player profile schema',
    )
  })

  it('rejects broken entity references', () => {
    const invalid = {
      ...profileFixture,
      poules: profileFixture.poules.map((poule) =>
        poule.poule_id === 300 ? { ...poule, season_id: 'missing-season' } : poule,
      ),
    }

    expect(() => parseProfileData(invalid)).toThrow(
      'Poule 300 refers to unknown season missing-season',
    )
  })
})

describe('profile selectors', () => {
  const index = parseProfileData(profileFixture)

  it('searches names, aliases, and player IDs without accent sensitivity', () => {
    expect(filterPlayers(index, {
      query: 'a. example',
      groupId: '',
      seasonId: '',
      teamQuery: '',
      className: '',
      pouleId: '',
    }).map((player) => player.player_id)).toEqual([1])

    expect(filterPlayers(index, {
      query: '3',
      groupId: '',
      seasonId: '',
      teamQuery: '',
      className: '',
      pouleId: '',
    }).map((player) => player.player_id)).toEqual([3])
  })

  it('combines season, group, team, class, and poule filters', () => {
    const result = filterPlayers(index, {
      query: '',
      groupId: 'senioren',
      seasonId: 'najaar_2026',
      teamQuery: 'seniors 2',
      className: 'Klasse 3',
      pouleId: '300',
    })

    expect(result.map((player) => player.player_id)).toEqual([2])
  })

  it('sorts appearances chronologically and resolves shared comparison contexts', () => {
    const adaAppearances = appearancesForPlayer(index, 1)

    expect(adaAppearances.map((appearance) => appearance.season.season_id)).toEqual([
      'voorjaar_2020',
      'najaar_2022',
      'najaar_2026',
    ])
    expect(latestAppearance(adaAppearances)?.poule.poule_id).toBe(300)
    expect(commonPouleContexts(index, [1, 2]).map((context) => context.pouleId)).toEqual([
      300,
    ])
    expect(commonPouleContexts(index, [2, 3])).toEqual([])
  })

  it('counts profile coverage without aggregating ranking totals', () => {
    expect(profileCoverage(profileFixture)).toEqual({
      playerCount: 3,
      appearanceCount: 5,
      seasonCount: 3,
      groupCount: 2,
    })
  })
})
