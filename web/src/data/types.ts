export interface PlayerProfileDocument {
  schema_version: '2.0'
  generated_at: string
  scope: {
    region: {
      region_id: 19
      name: string
    }
    history_range: {
      from_season_id: string
      through_season_id: string
    }
    player_population: 'all_unique_player_ids_with_a_ranking_record_included_seasons'
  }
  seasons: Season[]
  groups: Group[]
  teams: Team[]
  poules: Poule[]
  players: Player[]
}

export interface Season {
  season_id: string
  name: string
  year: number
  retrieved_at: string
  source_file: string
}

export interface Group {
  group_id: string
  name: string
}

export interface Team {
  team_id: number
  name: string
}

export interface Poule {
  poule_id: number
  season_id: string
  group_id: string
  class: string | null
  source: string
  team_ids: number[]
}

export interface RankingSnapshot {
  played: number | null
  wins: number | null
  win_pct: number | null
  rating: number | null
  prev_rating: number | null
  anonymous: boolean | null
  substitute: boolean | null
  own_team: boolean | null
}

export interface Appearance {
  poule_id: number
  team_id: number | null
  ranking: RankingSnapshot
}

export interface GroupHistory {
  group_id: string
  appearances: Appearance[]
}

export interface Player {
  player_id: number
  full_name: string
  name_aliases: string[]
  group_history: GroupHistory[]
}

export interface ResolvedAppearance extends Appearance {
  season: Season
  group: Group
  poule: Poule
  team: Team | null
}

export interface ProfileIndex {
  document: PlayerProfileDocument
  seasonsById: Map<string, Season>
  groupsById: Map<string, Group>
  teamsById: Map<number, Team>
  poulesById: Map<number, Poule>
  playersById: Map<number, Player>
  appearancesByPlayerId: Map<number, ResolvedAppearance[]>
}

export type TrendMetric = 'winPct' | 'rating'
