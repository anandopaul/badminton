import Ajv2020, { type AnySchema } from 'ajv/dist/2020'
import addFormats from 'ajv-formats'
import profileSchema from '../../../schema/player_profile.schema.draft.json'
import type {
  Appearance,
  Player,
  PlayerProfileDocument,
  ProfileIndex,
  ResolvedAppearance,
} from './types'

const ajv = new Ajv2020({ allErrors: true, strict: false })
addFormats(ajv)
const validateProfile = ajv.compile<PlayerProfileDocument>(
  profileSchema as AnySchema,
)

function assertProfileSchema(value: unknown): asserts value is PlayerProfileDocument {
  if (validateProfile(value)) return

  const details = (validateProfile.errors ?? [])
    .slice(0, 8)
    .map((error) => `${error.instancePath || '/'} ${error.message ?? 'is invalid'}`)
    .join('\n')
  const remaining = Math.max((validateProfile.errors?.length ?? 0) - 8, 0)
  throw new Error(
    `The selected file does not match the player profile schema.\n${details}${
      remaining > 0 ? `\n…and ${remaining} more issue(s).` : ''
    }`,
  )
}

function assertUniqueIds<T, K extends string | number>(
  records: T[],
  getId: (record: T) => K,
  label: string,
): Map<K, T> {
  const index = new Map<K, T>()
  for (const record of records) {
    const id = getId(record)
    if (index.has(id)) {
      throw new Error(`The profile data contains a duplicate ${label} ID: ${id}.`)
    }
    index.set(id, record)
  }
  return index
}

function resolveAppearance(
  appearance: Appearance,
  groupId: string,
  seasonsById: ProfileIndex['seasonsById'],
  groupsById: ProfileIndex['groupsById'],
  teamsById: ProfileIndex['teamsById'],
  poulesById: ProfileIndex['poulesById'],
): ResolvedAppearance {
  const poule = poulesById.get(appearance.poule_id)
  if (!poule) {
    throw new Error(
      `Player appearance refers to unknown poule ID ${appearance.poule_id}.`,
    )
  }
  if (poule.group_id !== groupId) {
    throw new Error(
      `Poule ${poule.poule_id} belongs to group ${poule.group_id}, not ${groupId}.`,
    )
  }

  const season = seasonsById.get(poule.season_id)
  if (!season) {
    throw new Error(
      `Poule ${poule.poule_id} refers to unknown season ${poule.season_id}.`,
    )
  }
  const group = groupsById.get(poule.group_id)
  if (!group) {
    throw new Error(
      `Poule ${poule.poule_id} refers to unknown group ${poule.group_id}.`,
    )
  }
  const team =
    appearance.team_id === null ? null : teamsById.get(appearance.team_id) ?? null
  if (appearance.team_id !== null && team === null) {
    throw new Error(
      `Poule ${poule.poule_id} refers to unknown team ${appearance.team_id}.`,
    )
  }
  if (appearance.team_id !== null && !poule.team_ids.includes(appearance.team_id)) {
    throw new Error(
      `Team ${appearance.team_id} is not listed in poule ${poule.poule_id}.`,
    )
  }

  return { ...appearance, season, group, poule, team }
}

function buildIndex(document: PlayerProfileDocument): ProfileIndex {
  const seasonsById = assertUniqueIds(
    document.seasons,
    (season) => season.season_id,
    'season',
  )
  const groupsById = assertUniqueIds(
    document.groups,
    (group) => group.group_id,
    'group',
  )
  const teamsById = assertUniqueIds(
    document.teams,
    (team) => team.team_id,
    'team',
  )
  const poulesById = assertUniqueIds(
    document.poules,
    (poule) => poule.poule_id,
    'poule',
  )
  const playersById = assertUniqueIds(
    document.players,
    (player) => player.player_id,
    'player',
  )

  for (const poule of document.poules) {
    if (!seasonsById.has(poule.season_id)) {
      throw new Error(
        `Poule ${poule.poule_id} refers to unknown season ${poule.season_id}.`,
      )
    }
    if (!groupsById.has(poule.group_id)) {
      throw new Error(
        `Poule ${poule.poule_id} refers to unknown group ${poule.group_id}.`,
      )
    }
    for (const teamId of poule.team_ids) {
      if (!teamsById.has(teamId)) {
        throw new Error(
          `Poule ${poule.poule_id} refers to unknown team ${teamId}.`,
        )
      }
    }
  }

  const appearancesByPlayerId = new Map<number, ResolvedAppearance[]>()
  for (const player of document.players) {
    const appearances = player.group_history.flatMap((history) => {
      if (!groupsById.has(history.group_id)) {
        throw new Error(
          `Player ${player.player_id} refers to unknown group ${history.group_id}.`,
        )
      }
      return history.appearances.map((appearance) =>
        resolveAppearance(
          appearance,
          history.group_id,
          seasonsById,
          groupsById,
          teamsById,
          poulesById,
        ),
      )
    })
    appearancesByPlayerId.set(player.player_id, appearances)
  }

  return {
    document,
    seasonsById,
    groupsById,
    teamsById,
    poulesById,
    playersById,
    appearancesByPlayerId,
  }
}

export function parseProfileData(value: unknown): ProfileIndex {
  assertProfileSchema(value)
  return buildIndex(value)
}

export async function loadLocalProfile(
  signal?: AbortSignal,
): Promise<ProfileIndex> {
  let response: Response
  try {
    response = await fetch('/local-data/player_profile.json', {
      cache: 'no-store',
      headers: { Accept: 'application/json' },
      signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw error
    }
    throw new Error(
      'Could not load local profile data. Start the app with `npm run dev` from the web directory.',
    )
  }

  let payload: unknown
  try {
    payload = await response.json()
  } catch {
    throw new Error(
      `The local profile endpoint returned invalid JSON (HTTP ${response.status}).`,
    )
  }

  if (!response.ok) {
    const message =
      typeof payload === 'object' &&
      payload !== null &&
      'error' in payload &&
      typeof payload.error === 'string'
        ? payload.error
        : `The local profile endpoint returned HTTP ${response.status}.`
    throw new Error(message)
  }

  return parseProfileData(payload)
}

export function getPlayer(
  index: ProfileIndex,
  playerId: number,
): Player | undefined {
  return index.playersById.get(playerId)
}
