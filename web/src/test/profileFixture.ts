import type { PlayerProfileDocument } from '../data/types'

const ranking = {
  played: 12,
  wins: 7,
  win_pct: 58.333,
  rating: null,
  prev_rating: null,
  anonymous: false,
  substitute: false,
  own_team: true,
} as const

export const profileFixture: PlayerProfileDocument = {
  schema_version: '2.0',
  generated_at: '2026-11-22T11:53:19Z',
  scope: {
    region: { region_id: 19, name: 'Example Region' },
    history_range: {
      from_season_id: 'voorjaar_2020',
      through_season_id: 'najaar_2026',
    },
    player_population:
      'all_unique_player_ids_with_a_ranking_record_included_seasons',
  },
  seasons: [
    {
      season_id: 'voorjaar_2020',
      name: 'voorjaar 2020',
      year: 2020,
      retrieved_at: '2026-11-22T10:00:00Z',
      source_file: 'output/2020/voorjaar_2020.json',
    },
    {
      season_id: 'najaar_2022',
      name: 'najaar 2022',
      year: 2022,
      retrieved_at: '2026-11-22T10:00:00Z',
      source_file: 'output/2022/najaar_2022.json',
    },
    {
      season_id: 'najaar_2026',
      name: 'najaar 2026',
      year: 2026,
      retrieved_at: '2026-11-22T10:00:00Z',
      source_file: 'output/2026/najaar_2026.json',
    },
  ],
  groups: [
    { group_id: 'jeugd', name: 'Jeugd' },
    { group_id: 'senioren', name: 'Senioren' },
  ],
  teams: [
    { team_id: 10, name: 'Sample Juniors 1' },
    { team_id: 20, name: 'Sample Seniors 1' },
    { team_id: 21, name: 'Sample Seniors 2' },
  ],
  poules: [
    {
      poule_id: 100,
      season_id: 'voorjaar_2020',
      group_id: 'jeugd',
      class: 'Klasse 2',
      source: 'https://badminton.now/poule/100',
      team_ids: [10],
    },
    {
      poule_id: 200,
      season_id: 'najaar_2022',
      group_id: 'senioren',
      class: 'Klasse 3',
      source: 'https://badminton.now/poule/200',
      team_ids: [20],
    },
    {
      poule_id: 300,
      season_id: 'najaar_2026',
      group_id: 'senioren',
      class: 'Klasse 3',
      source: 'https://badminton.now/poule/300',
      team_ids: [20, 21],
    },
  ],
  players: [
    {
      player_id: 1,
      full_name: 'Sample Ada',
      name_aliases: ['Á. Example'],
      group_history: [
        {
          group_id: 'jeugd',
          appearances: [{ poule_id: 100, team_id: 10, ranking }],
        },
        {
          group_id: 'senioren',
          appearances: [
            { poule_id: 200, team_id: 20, ranking },
            { poule_id: 300, team_id: 20, ranking: { ...ranking, played: 18 } },
          ],
        },
      ],
    },
    {
      player_id: 2,
      full_name: 'Sample Bo',
      name_aliases: [],
      group_history: [
        {
          group_id: 'senioren',
          appearances: [{ poule_id: 300, team_id: 21, ranking }],
        },
      ],
    },
    {
      player_id: 3,
      full_name: 'Sample Cato',
      name_aliases: ['C. Example'],
      group_history: [
        {
          group_id: 'jeugd',
          appearances: [
            {
              poule_id: 100,
              team_id: 10,
              ranking: { ...ranking, win_pct: null, anonymous: true },
            },
          ],
        },
      ],
    },
  ],
}
