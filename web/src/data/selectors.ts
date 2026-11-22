import type {
  Player,
  PlayerProfileDocument,
  ProfileIndex,
  ResolvedAppearance,
} from './types'

export interface PlayerFilters {
  query: string
  groupId: string
  seasonId: string
  teamQuery: string
  className: string
  pouleId: string
}

export interface ComparisonContext {
  pouleId: number
  seasonId: string
  groupId: string
  className: string | null
}

export function normalizeSearch(value: string): string {
  return value
    .normalize('NFD')
    .replace(/\p{Diacritic}/gu, '')
    .toLocaleLowerCase()
    .trim()
}

export function seasonOrder(season: { year: number; name: string }): number {
  const semester = normalizeSearch(season.name).startsWith('najaar') ? 1 : 0
  return season.year * 2 + semester
}

export function sortAppearances(
  appearances: ResolvedAppearance[],
): ResolvedAppearance[] {
  return [...appearances].sort((a, b) => {
    const seasonDifference = seasonOrder(a.season) - seasonOrder(b.season)
    if (seasonDifference !== 0) return seasonDifference
    const groupDifference = a.group.name.localeCompare(b.group.name)
    if (groupDifference !== 0) return groupDifference
    return a.poule.poule_id - b.poule.poule_id
  })
}

export function latestAppearance(
  appearances: ResolvedAppearance[],
): ResolvedAppearance | undefined {
  return sortAppearances(appearances).at(-1)
}

export function appearancesForPlayer(
  index: ProfileIndex,
  playerId: number,
): ResolvedAppearance[] {
  return sortAppearances(index.appearancesByPlayerId.get(playerId) ?? [])
}

function playerMatchesFilters(
  index: ProfileIndex,
  player: Player,
  filters: PlayerFilters,
): boolean {
  const query = normalizeSearch(filters.query)
  const textMatches =
    query.length === 0 ||
    normalizeSearch(
      [player.full_name, ...player.name_aliases, String(player.player_id)].join(' '),
    ).includes(query)
  if (!textMatches) return false

  const teamQuery = normalizeSearch(filters.teamQuery)
  return appearancesForPlayer(index, player.player_id).some((appearance) => {
    if (filters.groupId && appearance.group.group_id !== filters.groupId) {
      return false
    }
    if (filters.seasonId && appearance.season.season_id !== filters.seasonId) {
      return false
    }
    if (
      teamQuery &&
      !normalizeSearch(appearance.team?.name ?? '').includes(teamQuery)
    ) {
      return false
    }
    if (filters.className && appearance.poule.class !== filters.className) {
      return false
    }
    if (
      filters.pouleId &&
      String(appearance.poule.poule_id) !== filters.pouleId.trim()
    ) {
      return false
    }
    return true
  })
}

export function filterPlayers(
  index: ProfileIndex,
  filters: PlayerFilters,
): Player[] {
  return index.document.players
    .filter((player) => playerMatchesFilters(index, player, filters))
    .sort((a, b) => a.full_name.localeCompare(b.full_name))
}

export function commonPouleContexts(
  index: ProfileIndex,
  playerIds: number[],
): ComparisonContext[] {
  if (playerIds.length < 2) return []

  const appearances = playerIds.map((playerId) =>
    appearancesForPlayer(index, playerId),
  )
  if (appearances.some((items) => items.length === 0)) return []

  const firstPlayerContexts = new Map<number, ComparisonContext>()
  for (const appearance of appearances[0] ?? []) {
    firstPlayerContexts.set(appearance.poule.poule_id, {
      pouleId: appearance.poule.poule_id,
      seasonId: appearance.season.season_id,
      groupId: appearance.group.group_id,
      className: appearance.poule.class,
    })
  }

  const commonIds = [...firstPlayerContexts.keys()].filter((pouleId) =>
    appearances.slice(1).every((items) =>
      items.some((appearance) => appearance.poule.poule_id === pouleId),
    ),
  )
  return commonIds
    .map((pouleId) => firstPlayerContexts.get(pouleId))
    .filter((context): context is ComparisonContext => context !== undefined)
    .sort((a, b) => {
      const seasonA = index.seasonsById.get(a.seasonId)
      const seasonB = index.seasonsById.get(b.seasonId)
      const difference =
        seasonOrder(seasonA ?? { year: 0, name: '' }) -
        seasonOrder(seasonB ?? { year: 0, name: '' })
      return difference || a.pouleId - b.pouleId
    })
}

export function appearanceInPoule(
  index: ProfileIndex,
  playerId: number,
  pouleId: number,
): ResolvedAppearance | undefined {
  return appearancesForPlayer(index, playerId).find(
    (appearance) => appearance.poule.poule_id === pouleId,
  )
}

export function buildTrendPoints(
  appearances: ResolvedAppearance[],
  groupId: string,
) {
  return sortAppearances(
    appearances.filter((appearance) => appearance.group.group_id === groupId),
  ).map((appearance, position) => ({
    key: `${appearance.season.season_id}-${appearance.poule.poule_id}-${position}`,
    label: appearance.season.name,
    seasonId: appearance.season.season_id,
    groupName: appearance.group.name,
    teamName: appearance.team?.name ?? 'Unknown team',
    className: appearance.poule.class ?? 'Unclassified',
    pouleId: appearance.poule.poule_id,
    played: appearance.ranking.played,
    wins: appearance.ranking.wins,
    winPct: appearance.ranking.win_pct,
    rating: appearance.ranking.rating,
    prevRating: appearance.ranking.prev_rating,
  }))
}

export function profileCoverage(document: PlayerProfileDocument): {
  playerCount: number
  appearanceCount: number
  seasonCount: number
  groupCount: number
} {
  return {
    playerCount: document.players.length,
    appearanceCount: document.players.reduce(
      (total, player) =>
        total +
        player.group_history.reduce(
          (groupTotal, history) => groupTotal + history.appearances.length,
          0,
        ),
      0,
    ),
    seasonCount: document.seasons.length,
    groupCount: document.groups.length,
  }
}
