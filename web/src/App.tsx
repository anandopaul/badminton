import {
  Suspense,
  lazy,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react'
import {
  Activity,
  ArrowLeftRight,
  CalendarDays,
  ChartNoAxesCombined,
  ChevronDown,
  ChevronRight,
  CircleAlert,
  Database,
  MessageCircle,
  Search,
  ShieldCheck,
  Sparkles,
  Users,
  X,
} from 'lucide-react'
import {
  appearancesForPlayer,
  buildTrendPoints,
  commonPouleContexts,
  filterPlayers,
  latestAppearance,
  profileCoverage,
  seasonOrder,
  sortAppearances,
  normalizeSearch,
} from './data/selectors'
import { loadLocalProfile } from './data/profileData'
import ChatPanel from './components/ChatPanel'
import type {
  Player,
  ProfileIndex,
  ResolvedAppearance,
  TrendMetric,
} from './data/types'
import './App.css'

type ViewName = 'explore' | 'compare' | 'ask'
type MetricName = TrendMetric
type SortMode = 'name' | 'recent' | 'history'

const TrendChart = lazy(() => import('./components/TrendChart'))

interface Filters {
  query: string
  groupId: string
  seasonId: string
  teamQuery: string
  className: string
  pouleId: string
}

const EMPTY_FILTERS: Filters = {
  query: '',
  groupId: '',
  seasonId: '',
  teamQuery: '',
  className: '',
  pouleId: '',
}

function formatRate(value: number | null): string {
  return value === null ? '—' : `${value.toFixed(1)}%`
}

function formatRating(value: number | null): string {
  return value === null ? '—' : value.toFixed(2)
}

function formatCount(value: number | null): string {
  return value === null ? '—' : value.toLocaleString()
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  return parts.length === 0
    ? '??'
    : parts
        .slice(0, 2)
        .map((part) => part[0]?.toLocaleUpperCase() ?? '')
        .join('')
}

function displayName(player: Player, appearances: ResolvedAppearance[]): string {
  const isAlwaysAnonymous =
    appearances.length > 0 &&
    appearances.every((appearance) => appearance.ranking.anonymous === true)
  return isAlwaysAnonymous
    ? `Anonymous player ${player.player_id}`
    : player.full_name || `Player ${player.player_id}`
}

function groupClass(groupId: string): string {
  return `group-${normalizeSearch(groupId).replace(/[^a-z0-9]+/g, '-')}`
}

function movementSummary(appearances: ResolvedAppearance[]) {
  const ordered = sortAppearances(appearances)
  const seenSeasons = new Set<string>()
  const seasons: ResolvedAppearance[] = []
  for (const appearance of ordered) {
    if (seenSeasons.has(appearance.season.season_id)) continue
    seenSeasons.add(appearance.season.season_id)
    seasons.push(appearance)
  }

  const transitions = []
  for (let index = 1; index < seasons.length; index += 1) {
    const previous = seasons[index - 1]
    const current = seasons[index]
    if (previous && current && previous.group.group_id !== current.group.group_id) {
      transitions.push({
        from: previous.group.name,
        to: current.group.name,
        fromSeason: previous.season.name,
        toSeason: current.season.name,
      })
    }
  }
  return transitions
}

function App() {
  const [profileIndex, setProfileIndex] = useState<ProfileIndex | null>(null)
  const [loadError, setLoadError] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [reloadKey, setReloadKey] = useState(0)
  const [filters, setFilters] = useState<Filters>(EMPTY_FILTERS)
  const [sortMode, setSortMode] = useState<SortMode>('name')
  const [selectedPlayerId, setSelectedPlayerId] = useState<number | null>(null)
  const [comparePlayerIds, setComparePlayerIds] = useState<number[]>([])
  const [compareMessage, setCompareMessage] = useState<string | null>(null)
  const [view, setView] = useState<ViewName>('explore')

  useEffect(() => {
    const controller = new AbortController()
    void loadLocalProfile(controller.signal)
      .then((index) => {
        setProfileIndex(index)
        setIsLoading(false)
        setSelectedPlayerId((current) =>
          current !== null && index.playersById.has(current)
            ? current
            : index.document.players[0]?.player_id ?? null,
        )
      })
      .catch((error: unknown) => {
        if (error instanceof DOMException && error.name === 'AbortError') return
        setLoadError(
          error instanceof Error ? error.message : 'Profile data could not be loaded.',
        )
        setIsLoading(false)
      })

    return () => controller.abort()
  }, [reloadKey])

  const visiblePlayers = useMemo(() => {
    if (!profileIndex) return []
    const players = filterPlayers(profileIndex, filters)
    if (sortMode === 'history') {
      return players.sort((a, b) => {
        const historyA = profileIndex.appearancesByPlayerId.get(a.player_id)?.length ?? 0
        const historyB = profileIndex.appearancesByPlayerId.get(b.player_id)?.length ?? 0
        return historyB - historyA || a.full_name.localeCompare(b.full_name)
      })
    }
    if (sortMode === 'recent') {
      return players.sort((a, b) => {
        const latestA = latestAppearance(
          profileIndex.appearancesByPlayerId.get(a.player_id) ?? [],
        )
        const latestB = latestAppearance(
          profileIndex.appearancesByPlayerId.get(b.player_id) ?? [],
        )
        const orderA = latestA ? seasonOrder(latestA.season) : 0
        const orderB = latestB ? seasonOrder(latestB.season) : 0
        return orderB - orderA || a.full_name.localeCompare(b.full_name)
      })
    }
    return players
  }, [profileIndex, filters, sortMode])

  const selectedPlayer =
    visiblePlayers.find((player) => player.player_id === selectedPlayerId) ??
    visiblePlayers[0]

  const coverage = useMemo(
    () => (profileIndex ? profileCoverage(profileIndex.document) : null),
    [profileIndex],
  )

  function setFilter<K extends keyof Filters>(key: K, value: Filters[K]) {
    setFilters((current) => ({ ...current, [key]: value }))
  }

  function reloadProfile() {
    setIsLoading(true)
    setLoadError(null)
    setReloadKey((key) => key + 1)
  }

  function toggleComparison(playerId: number) {
    setCompareMessage(null)
    if (
      !comparePlayerIds.includes(playerId) &&
      comparePlayerIds.length >= 3
    ) {
      setCompareMessage('Compare up to three players at a time.')
      return
    }
    setComparePlayerIds((current) => {
      if (current.includes(playerId)) {
        return current.filter((id) => id !== playerId)
      }
      return [...current, playerId]
    })
  }

  if (isLoading) {
    return (
      <div className="loading-screen">
        <div className="loading-mark">RA</div>
        <p>Opening the local player archive…</p>
        <span className="loading-bar" />
      </div>
    )
  }

  if (loadError || !profileIndex) {
    return (
      <div className="error-screen">
        <div className="error-card">
          <div className="error-icon">
            <CircleAlert size={22} />
          </div>
          <p className="eyebrow">LOCAL DATA CONNECTION</p>
          <h1>Couldn’t open the player archive.</h1>
          <p className="error-copy">
            {loadError ?? 'The local profile data is not available.'}
          </p>
          <button
            className="button button-primary"
            onClick={reloadProfile}
            type="button"
          >
            Try again
          </button>
          <p className="error-footnote">
            This app reads only <code>output/player_profile.json</code> from the
            local development server. It does not contact Badminton NOW.
          </p>
        </div>
      </div>
    )
  }

  const seasons = [...profileIndex.document.seasons].sort(
    (a, b) => seasonOrder(a) - seasonOrder(b),
  )
  const groups = [...profileIndex.document.groups].sort((a, b) =>
    a.name.localeCompare(b.name),
  )
  const classNames = [
    ...new Set(
      profileIndex.document.poules
        .map((poule) => poule.class)
        .filter((name): name is string => Boolean(name)),
    ),
  ].sort((a, b) => a.localeCompare(b))

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-lockup">
          <div className="brand-mark">RA</div>
          <div>
            <p className="brand-name">RALLY ATLAS</p>
            <p className="brand-caption">Player history, in perspective</p>
          </div>
        </div>
        <div className="topbar-right">
          <div className="local-badge">
            <span className="local-dot" />
            LOCAL ONLY
          </div>
          <button
            className="icon-button reload-button"
            onClick={reloadProfile}
            type="button"
            title="Reload local profile data"
            aria-label="Reload local profile data"
          >
            <Database size={16} />
            <span>Refresh data</span>
          </button>
        </div>
      </header>

      <main className="workspace">
        <aside className="directory-panel">
          <div className="directory-intro">
            <div className="directory-kicker">
              <span className="kicker-line" />
              THE PLAYER INDEX
            </div>
            <h1>Find a story.</h1>
            <p>
              Explore ranking histories across <strong>{coverage?.seasonCount}</strong>{' '}
              seasons and <strong>{coverage?.groupCount}</strong> competition
              groups.
            </p>
          </div>

          <label className="search-field">
            <Search size={17} aria-hidden="true" />
            <span className="visually-hidden">Search by name, alias, or player ID</span>
            <input
              autoComplete="off"
              onChange={(event) => setFilter('query', event.target.value)}
              placeholder="Name, alias or player ID"
              type="search"
              value={filters.query}
            />
            <kbd>/</kbd>
          </label>

          <details className="filter-disclosure">
            <summary>
              <span>
                <span className="filter-count">{coverage?.playerCount.toLocaleString()}</span>
                players in this archive
              </span>
              <ChevronDown size={16} />
            </summary>
            <div className="filter-grid">
              <label className="filter-control">
                <span>Competition group</span>
                <select
                  onChange={(event) => setFilter('groupId', event.target.value)}
                  value={filters.groupId}
                >
                  <option value="">All groups</option>
                  {groups.map((group) => (
                    <option key={group.group_id} value={group.group_id}>
                      {group.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-control">
                <span>Season</span>
                <select
                  onChange={(event) => setFilter('seasonId', event.target.value)}
                  value={filters.seasonId}
                >
                  <option value="">All seasons</option>
                  {seasons.map((season) => (
                    <option key={season.season_id} value={season.season_id}>
                      {season.name}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-control">
                <span>Team name</span>
                <input
                  onChange={(event) => setFilter('teamQuery', event.target.value)}
                  placeholder="e.g. ABC 3"
                  type="search"
                  value={filters.teamQuery}
                />
              </label>
              <label className="filter-control">
                <span>Class</span>
                <select
                  onChange={(event) => setFilter('className', event.target.value)}
                  value={filters.className}
                >
                  <option value="">All classes</option>
                  {classNames.map((className) => (
                    <option key={className} value={className}>
                      {className}
                    </option>
                  ))}
                </select>
              </label>
              <label className="filter-control filter-control-wide">
                <span>Poule ID</span>
                <input
                  inputMode="numeric"
                  onChange={(event) => setFilter('pouleId', event.target.value)}
                  placeholder="Filter by exact poule ID"
                  type="search"
                  value={filters.pouleId}
                />
              </label>
              <button
                className="clear-filters"
                onClick={() => setFilters(EMPTY_FILTERS)}
                type="button"
              >
                Clear filters
              </button>
            </div>
          </details>

          <div className="list-toolbar">
            <span>
              <strong>{visiblePlayers.length.toLocaleString()}</strong> MATCHING
            </span>
            <label>
              <span className="visually-hidden">Sort players</span>
              <select
                aria-label="Sort players"
                onChange={(event) => {
                  const value = event.target.value
                  if (value === 'name' || value === 'recent' || value === 'history') {
                    setSortMode(value)
                  }
                }}
                value={sortMode}
              >
                <option value="name">A–Z</option>
                <option value="recent">Recently active</option>
                <option value="history">Most history</option>
              </select>
            </label>
          </div>

          <nav className="player-list" aria-label="Player directory">
            {visiblePlayers.length === 0 ? (
              <div className="empty-list">
                <Search size={19} />
                <p>No players match these filters.</p>
                <button onClick={() => setFilters(EMPTY_FILTERS)} type="button">
                  Reset search
                </button>
              </div>
            ) : (
              visiblePlayers.map((player) => {
                const appearances = appearancesForPlayer(
                  profileIndex,
                  player.player_id,
                )
                const latest = latestAppearance(appearances)
                const name = displayName(player, appearances)
                const isSelected =
                  view === 'explore' && player.player_id === selectedPlayer?.player_id

                return (
                  <button
                    aria-current={isSelected ? 'true' : undefined}
                    className={`player-list-item${isSelected ? ' is-selected' : ''}`}
                    key={player.player_id}
                    onClick={() => {
                      setSelectedPlayerId(player.player_id)
                      setView('explore')
                    }}
                    type="button"
                  >
                    <span className={`player-avatar ${latest ? groupClass(latest.group.group_id) : ''}`}>
                      {initials(name)}
                    </span>
                    <span className="player-list-copy">
                      <span className="player-list-name">{name}</span>
                      <span className="player-list-meta">
                        {latest
                          ? `${latest.team?.name ?? 'Unknown team'} · ${latest.season.name}`
                          : `Player ${player.player_id}`}
                      </span>
                    </span>
                    <ChevronRight className="player-chevron" size={16} />
                  </button>
                )
              })
            )}
          </nav>

          <div className="directory-foot">
            <span className="privacy-lock"><ShieldCheck size={14} /></span>
            <p>Loaded from this machine. Nothing is uploaded.</p>
          </div>
        </aside>

        <section className="main-panel">
          <div className="main-toolbar">
            <div className="breadcrumbs">
              <span>REGION 19</span>
              <ChevronRight size={13} />
              <span>
                {view === 'compare'
                  ? 'PLAYER COMPARISON'
                  : view === 'ask'
                    ? 'ASK RALLY ATLAS'
                    : 'PLAYER PROFILE'}
              </span>
            </div>
            <nav className="view-tabs" aria-label="Explorer views">
              <button
                aria-current={view === 'explore' ? 'page' : undefined}
                className={view === 'explore' ? 'is-active' : ''}
                onClick={() => setView('explore')}
                type="button"
              >
                <Activity size={15} />
                Explore
              </button>
              <button
                aria-current={view === 'compare' ? 'page' : undefined}
                className={view === 'compare' ? 'is-active' : ''}
                onClick={() => setView('compare')}
                type="button"
              >
                <ArrowLeftRight size={15} />
                Compare
                {comparePlayerIds.length > 0 && (
                  <span className="tab-count">{comparePlayerIds.length}</span>
                )}
              </button>
              <button
                aria-current={view === 'ask' ? 'page' : undefined}
                className={view === 'ask' ? 'is-active' : ''}
                onClick={() => setView('ask')}
                type="button"
              >
                <MessageCircle size={15} />
                Ask
              </button>
            </nav>
          </div>

          {view === 'compare' ? (
            <ComparisonView
              compareMessage={compareMessage}
              index={profileIndex}
              playerIds={comparePlayerIds}
              onRemove={toggleComparison}
              onReturn={() => setView('explore')}
            />
          ) : view === 'explore' && selectedPlayer ? (
            <PlayerDetail
              comparePlayerIds={comparePlayerIds}
              index={profileIndex}
              onToggleCompare={toggleComparison}
              player={selectedPlayer}
            />
          ) : view === 'explore' ? (
            <div className="no-player-selected">
              <div className="empty-emblem"><Users size={24} /></div>
              <h2>No player selected</h2>
              <p>Choose a player or adjust the filters to see their history.</p>
            </div>
          ) : null}

          <div
            aria-hidden={view !== 'ask'}
            className={`chat-view${view === 'ask' ? '' : ' is-hidden'}`}
          >
            <ChatPanel
              selectedPlayerId={selectedPlayer?.player_id ?? null}
              selectedPlayerName={
                selectedPlayer && profileIndex
                  ? displayName(
                      selectedPlayer,
                      appearancesForPlayer(profileIndex, selectedPlayer.player_id),
                    )
                  : null
              }
            />
          </div>

          <footer className="data-footer">
            <span>
              DATA GENERATED {new Date(profileIndex.document.generated_at).toLocaleString()}
            </span>
            <span>SCHEMA {profileIndex.document.schema_version}</span>
            <span>
              {coverage?.appearanceCount.toLocaleString()} RANKING APPEARANCES
            </span>
          </footer>
        </section>
      </main>
    </div>
  )
}

function PlayerDetail({
  index,
  player,
  comparePlayerIds,
  onToggleCompare,
}: {
  index: ProfileIndex
  player: Player
  comparePlayerIds: number[]
  onToggleCompare: (playerId: number) => void
}) {
  const appearances = useMemo(
    () => appearancesForPlayer(index, player.player_id),
    [index, player.player_id],
  )
  const groups = useMemo(
    () =>
      [
        ...new Map(
          appearances.map((appearance) => [
            appearance.group.group_id,
            appearance.group,
          ]),
        ).values(),
      ].sort((a, b) => a.name.localeCompare(b.name)),
    [appearances],
  )
  const latest = useMemo(() => latestAppearance(appearances), [appearances])
  const [groupView, setGroupView] = useState<{
    playerId: number
    groupId: string
    metric: MetricName
  } | null>(null)
  const savedGroupView =
    groupView?.playerId === player.player_id ? groupView : null
  const groupId = groups.some((group) => group.group_id === savedGroupView?.groupId)
    ? savedGroupView?.groupId ?? ''
    : latest?.group.group_id ?? groups[0]?.group_id ?? ''
  const groupAppearances = appearances.filter(
    (appearance) => appearance.group.group_id === groupId,
  )
  const latestInGroup = latestAppearance(groupAppearances)
  const trendPoints = buildTrendPoints(appearances, groupId)
  const hasRating = trendPoints.some((point) => point.rating !== null)
  const metric = savedGroupView?.metric ?? 'winPct'
  const isInComparison = comparePlayerIds.includes(player.player_id)
  const name = displayName(player, appearances)
  const transitions = movementSummary(appearances)

  function updateGroup(groupId: string) {
    setGroupView({ playerId: player.player_id, groupId, metric })
  }

  function updateMetric(metric: MetricName) {
    setGroupView({ playerId: player.player_id, groupId, metric })
  }

  const metricValue =
    metric === 'winPct'
      ? (point: (typeof trendPoints)[number]) => point.winPct
      : (point: (typeof trendPoints)[number]) => point.rating

  return (
    <div className="profile-view">
      <section className="profile-hero">
        <div className="profile-hero-main">
          <div className={`profile-avatar ${latest ? groupClass(latest.group.group_id) : ''}`}>
            {initials(name)}
          </div>
          <div className="profile-title">
            <p className="eyebrow">PLAYER PROFILE <span>·</span> ID {player.player_id}</p>
            <h1>{name}</h1>
            {player.name_aliases.length > 0 && (
              <p className="alias-line">
                Also listed as {player.name_aliases.join(', ')}
              </p>
            )}
            {latest && (
              <div className="latest-tags">
                <span className="group-tag">{latest.group.name}</span>
                <span>{latest.team?.name ?? 'Team not listed'}</span>
                <span className="tag-divider">/</span>
                <span>{latest.poule.class ?? 'Unclassified'}</span>
                <span className="tag-divider">/</span>
                <span>{latest.season.name}</span>
              </div>
            )}
          </div>
        </div>
        <div className="profile-hero-actions">
          <button
            className={`button ${isInComparison ? 'button-added' : 'button-secondary'}`}
            onClick={() => onToggleCompare(player.player_id)}
            type="button"
          >
            {isInComparison ? <X size={15} /> : <ArrowLeftRight size={15} />}
            {isInComparison ? 'Remove from compare' : 'Add to compare'}
          </button>
        </div>
      </section>

      {transitions.length > 0 && (
        <section className="movement-note">
          <div className="movement-icon"><Sparkles size={16} /></div>
          <div>
            <strong>Group changes recorded</strong>
            <span>
              {transitions.map((transition, position) => (
                <span key={`${transition.fromSeason}-${transition.toSeason}`}>
                  {position > 0 && <span className="transition-separator"> · </span>}
                  {transition.from} → {transition.to}
                  <small> {transition.fromSeason} to {transition.toSeason}</small>
                </span>
              ))}
            </span>
          </div>
          <span className="movement-caveat">Observed categories · not a promotion label</span>
        </section>
      )}

      <section className="snapshot-section">
        <div className="section-heading">
          <div>
            <p className="eyebrow">LATEST SNAPSHOT</p>
            <h2>{latestInGroup?.season.name ?? 'No ranking snapshot'}</h2>
          </div>
          <label className="group-select">
            <span>View group</span>
            <select
              onChange={(event) => updateGroup(event.target.value)}
              value={groupId}
            >
              {groups.map((group) => (
                <option key={group.group_id} value={group.group_id}>
                  {group.name}
                </option>
              ))}
            </select>
            <ChevronDown size={14} />
          </label>
        </div>
        <div className="metric-grid">
          <MetricCard
            icon={<CalendarDays size={16} />}
            label="Played"
            value={formatCount(latestInGroup?.ranking.played ?? null)}
            note="in this ranking snapshot"
          />
          <MetricCard
            icon={<Activity size={16} />}
            label="Wins"
            value={formatCount(latestInGroup?.ranking.wins ?? null)}
            note="individual wins shown"
          />
          <MetricCard
            accent
            icon={<ChartNoAxesCombined size={16} />}
            label="Win rate"
            value={formatRate(latestInGroup?.ranking.win_pct ?? null)}
            note="as reported by the source"
          />
          <MetricCard
            icon={<Sparkles size={16} />}
            label="Rating"
            value={formatRating(latestInGroup?.ranking.rating ?? null)}
            note={
              latestInGroup?.ranking.rating !== null &&
              latestInGroup?.ranking.prev_rating !== null &&
              latestInGroup
                ? `Previous ${formatRating(latestInGroup.ranking.prev_rating)}`
                : 'not recorded in this snapshot'
            }
          />
        </div>
        <p className="snapshot-footnote">
          These are per-poule ranking snapshots, not lifetime totals or
          match-by-match results.
        </p>
      </section>

      <CareerTimeline
        appearances={appearances}
        index={index}
      />

      <section className="panel-card trend-panel">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">FORM OVER TIME</p>
            <h2>{groups.find((group) => group.group_id === groupId)?.name ?? 'Group'} snapshots</h2>
            <p className="panel-subtitle">
              Compare reported snapshots within this group. Missing seasons stay
              visible as gaps in the history table below.
            </p>
          </div>
          <div className="segmented-control" aria-label="Trend metric">
            <button
              aria-pressed={metric === 'winPct'}
              className={metric === 'winPct' ? 'is-active' : ''}
              onClick={() => updateMetric('winPct')}
              type="button"
            >
              Win rate
            </button>
            <button
              aria-pressed={metric === 'rating'}
              className={metric === 'rating' ? 'is-active' : ''}
              disabled={!hasRating}
              onClick={() => updateMetric('rating')}
              type="button"
            >
              Rating
            </button>
          </div>
        </div>
        {trendPoints.length === 0 || !trendPoints.some((point) => metricValue(point) !== null) ? (
          <div className="chart-empty">
            <ChartNoAxesCombined size={20} />
            <p>No {metric === 'winPct' ? 'win-rate' : 'rating'} values are recorded for this group.</p>
          </div>
        ) : (
          <Suspense
            fallback={
              <div className="chart-empty">
                <ChartNoAxesCombined size={20} />
                <p>Loading chart…</p>
              </div>
            }
          >
            <TrendChart metric={metric} points={trendPoints} />
          </Suspense>
        )}
        <div className="chart-legend">
          <span className="legend-dot" />
          <span>{metric === 'winPct' ? 'Win rate' : 'Rating'} in each source snapshot</span>
          <span className="legend-note">Hover a point for source context</span>
        </div>
      </section>

      <section className="panel-card history-panel">
        <div className="panel-heading history-heading">
          <div>
            <p className="eyebrow">SOURCE RECORDS</p>
            <h2>Season-by-season detail</h2>
          </div>
          <span className="record-count">{groupAppearances.length} appearances</span>
        </div>
        <div className="history-table-wrap">
          <table className="history-table">
            <thead>
              <tr>
                <th scope="col">Season</th>
                <th scope="col">Team · class</th>
                <th scope="col">Played</th>
                <th scope="col">Wins</th>
                <th scope="col">Win rate</th>
                <th scope="col">Rating</th>
                <th scope="col">Source</th>
              </tr>
            </thead>
            <tbody>
              {[...groupAppearances].reverse().map((appearance) => (
                <tr key={`${appearance.season.season_id}-${appearance.poule.poule_id}`}>
                  <td>
                    <span className="table-season">{appearance.season.name}</span>
                    <span className="table-group">{appearance.group.name}</span>
                  </td>
                  <td>
                    <span className="table-team">{appearance.team?.name ?? 'Unknown team'}</span>
                    <span className="table-class">
                      {appearance.poule.class ?? 'Unclassified'} · poule {appearance.poule.poule_id}
                    </span>
                  </td>
                  <td>{formatCount(appearance.ranking.played)}</td>
                  <td>{formatCount(appearance.ranking.wins)}</td>
                  <td>
                    <span className="rate-value">{formatRate(appearance.ranking.win_pct)}</span>
                  </td>
                  <td>{formatRating(appearance.ranking.rating)}</td>
                  <td>
                    <span className="source-file" title={appearance.season.source_file}>
                      {appearance.season.source_file.split('/').at(-1)}
                    </span>
                    {appearance.ranking.anonymous && (
                      <span className="anonymous-note">Anonymous snapshot</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="history-note">
          <CircleAlert size={15} />
          <span>
            Values are preserved per poule snapshot. Do not add them across
            seasons as a career total.
          </span>
        </div>
      </section>
    </div>
  )
}

function MetricCard({
  icon,
  label,
  value,
  note,
  accent = false,
}: {
  icon: ReactNode
  label: string
  value: string
  note: string
  accent?: boolean
}) {
  return (
    <article className={`metric-card${accent ? ' metric-card-accent' : ''}`}>
      <div className="metric-top">
        <span className="metric-icon">{icon}</span>
        <span>{label}</span>
      </div>
      <strong className="metric-value">{value}</strong>
      <span className="metric-note">{note}</span>
    </article>
  )
}

function CareerTimeline({
  index,
  appearances,
}: {
  index: ProfileIndex
  appearances: ResolvedAppearance[]
}) {
  const seasons = [...index.document.seasons].sort(
    (a, b) => seasonOrder(a) - seasonOrder(b),
  )
  const observedGroupIds = new Set(appearances.map((appearance) => appearance.group.group_id))
  const groups = index.document.groups
    .filter((group) => observedGroupIds.has(group.group_id))
    .sort((a, b) => a.name.localeCompare(b.name))

  return (
    <section className="panel-card timeline-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">THE LONG VIEW</p>
          <h2>Career map</h2>
          <p className="panel-subtitle">
            Each marker is a recorded ranking appearance. Empty cells mean no
            appearance in this export.
          </p>
        </div>
        <div className="timeline-key">
          <span className="timeline-key-dot" />
          <span>Recorded appearance</span>
        </div>
      </div>
      <div className="timeline-scroll" tabIndex={0} aria-label="Scrollable career timeline">
        <div
          className="timeline-grid"
          style={{
            gridTemplateColumns: `110px repeat(${seasons.length}, minmax(84px, 1fr))`,
          }}
        >
          <div className="timeline-corner">GROUP / SEASON</div>
          {seasons.map((season) => (
            <div className="timeline-season" key={season.season_id}>
              <span>{season.name.replace(' ', '\n')}</span>
            </div>
          ))}
          {groups.map((group) => (
            <TimelineLane
              appearances={appearances}
              group={group}
              key={group.group_id}
              seasons={seasons}
            />
          ))}
        </div>
      </div>
    </section>
  )
}

function TimelineLane({
  appearances,
  group,
  seasons,
}: {
  appearances: ResolvedAppearance[]
  group: ProfileIndex['document']['groups'][number]
  seasons: ProfileIndex['document']['seasons']
}) {
  return (
    <>
      <div className={`timeline-group-label ${groupClass(group.group_id)}`}>
        <span className="timeline-group-dot" />
        {group.name}
      </div>
      {seasons.map((season) => {
        const records = appearances.filter(
          (appearance) =>
            appearance.group.group_id === group.group_id &&
            appearance.season.season_id === season.season_id,
        )
        return (
          <div
            className={`timeline-cell${records.length > 0 ? ' has-record' : ''}`}
            key={`${group.group_id}-${season.season_id}`}
            title={
              records.length > 0
                ? records
                    .map(
                      (record) =>
                        `${record.season.name}: ${record.team?.name ?? 'Unknown team'}, ${record.poule.class ?? 'Unclassified'} (poule ${record.poule.poule_id})`,
                    )
                    .join('\n')
                : `${season.name}: no ranking appearance in this export`
            }
          >
            {records.map((record) => (
              <span className="timeline-node" key={record.poule.poule_id}>
                <span className="timeline-node-dot" />
                <span>{record.team?.name ?? 'Unknown'}</span>
              </span>
            ))}
          </div>
        )
      })}
    </>
  )
}

function ComparisonView({
  index,
  playerIds,
  onRemove,
  onReturn,
  compareMessage,
}: {
  index: ProfileIndex
  playerIds: number[]
  onRemove: (playerId: number) => void
  onReturn: () => void
  compareMessage: string | null
}) {
  const [selectedPouleId, setSelectedPouleId] = useState<number | null>(null)
  const contexts = commonPouleContexts(index, playerIds)
  const selectedContext =
    contexts.find((context) => context.pouleId === selectedPouleId) ?? contexts[0]
  const rows = selectedContext
    ? playerIds
        .map((playerId) => {
          const player = index.playersById.get(playerId)
          const appearance = appearancesForPlayer(index, playerId).find(
            (item) => item.poule.poule_id === selectedContext.pouleId,
          )
          return player && appearance
            ? {
                player,
                appearance,
                name: displayName(player, appearancesForPlayer(index, playerId)),
              }
            : null
        })
        .filter((row): row is NonNullable<typeof row> => row !== null)
    : []
  const cohort = selectedContext
    ? [...index.appearancesByPlayerId.entries()]
        .map(([playerId, appearances]) => {
          const appearance = appearances.find(
            (item) => item.poule.poule_id === selectedContext.pouleId,
          )
          const player = index.playersById.get(playerId)
          return player && appearance
            ? { playerId, appearance, player }
            : null
        })
        .filter((row): row is NonNullable<typeof row> => row !== null)
    : []

  const cohortRates = cohort
    .map((row) => row.appearance.ranking.win_pct)
    .filter((value): value is number => value !== null)
    .sort((a, b) => a - b)
  const middle = Math.floor(cohortRates.length / 2)
  const cohortMedian =
    cohortRates.length === 0
      ? null
      : cohortRates.length % 2 === 0
        ? ((cohortRates[middle - 1] ?? 0) + (cohortRates[middle] ?? 0)) / 2
        : (cohortRates[middle] ?? null)
  const season = selectedContext
    ? index.seasonsById.get(selectedContext.seasonId)
    : undefined
  const group = selectedContext
    ? index.groupsById.get(selectedContext.groupId)
    : undefined

  return (
    <div className="compare-view">
      <div className="compare-intro">
        <div>
          <p className="eyebrow">SIDE-BY-SIDE ANALYSIS</p>
          <h1>Compare the context.</h1>
          <p>
            Compare players only when their snapshots come from the same
            competition poule.
          </p>
        </div>
        <div className="compare-intro-icon"><ArrowLeftRight size={22} /></div>
      </div>

      <section className="panel-card compare-selection">
        <div className="panel-heading">
          <div>
            <p className="eyebrow">SELECTED PLAYERS</p>
            <h2>{playerIds.length} of 3 players</h2>
          </div>
          <button className="text-button" onClick={onReturn} type="button">
            <ChevronRight size={15} />
            Back to explorer
          </button>
        </div>
        {compareMessage && <p className="inline-notice">{compareMessage}</p>}
        {playerIds.length === 0 ? (
          <div className="compare-empty">
            <Users size={20} />
            <p>Add players from their profile page to start a comparison.</p>
            <button className="button button-secondary" onClick={onReturn} type="button">
              Browse players
            </button>
          </div>
        ) : (
          <>
            <div className="compare-chip-list">
              {playerIds.map((playerId) => {
                const player = index.playersById.get(playerId)
                if (!player) return null
                const appearances = appearancesForPlayer(index, playerId)
                const name = displayName(player, appearances)
                return (
                  <div className="compare-chip" key={playerId}>
                    <span className="mini-avatar">{initials(name)}</span>
                    <span>
                      <strong>{name}</strong>
                      <small>ID {playerId}</small>
                    </span>
                    <button
                      aria-label={`Remove ${name} from comparison`}
                      className="chip-remove"
                      onClick={() => onRemove(playerId)}
                      type="button"
                    >
                      <X size={14} />
                    </button>
                  </div>
                )
              })}
            </div>
            {playerIds.length < 2 ? (
              <p className="compare-hint">
                Add at least one more player. Use the directory search to find a
                player, then choose “Add to compare”.
              </p>
            ) : contexts.length === 0 ? (
              <div className="no-common-context">
                <CircleAlert size={18} />
                <p>
                  These players have no shared poule in the available data.
                  Comparing different groups or classes would not be a fair
                  like-for-like view.
                </p>
              </div>
            ) : (
              <label className="context-select">
                <span>Shared snapshot context</span>
                <select
                  onChange={(event) =>
                    setSelectedPouleId(Number(event.target.value))
                  }
                  value={selectedContext?.pouleId ?? ''}
                >
                  {contexts.map((context) => {
                    const itemSeason = index.seasonsById.get(context.seasonId)
                    const itemGroup = index.groupsById.get(context.groupId)
                    return (
                      <option key={context.pouleId} value={context.pouleId}>
                        {itemSeason?.name ?? context.seasonId} · {itemGroup?.name ?? context.groupId} · {context.className ?? 'Unclassified'} · poule {context.pouleId}
                      </option>
                    )
                  })}
                </select>
                <ChevronDown size={15} />
              </label>
            )}
          </>
        )}
      </section>

      {selectedContext && rows.length >= 2 && (
        <>
          <section className="compare-context-banner">
            <div className="context-icon"><CalendarDays size={17} /></div>
            <div>
              <span>LIKE-FOR-LIKE SNAPSHOT</span>
              <strong>
                {season?.name} <i>/</i> {group?.name} <i>/</i>{' '}
                {selectedContext.className ?? 'Unclassified'}
              </strong>
            </div>
            <span className="context-poule">POULE {selectedContext.pouleId}</span>
          </section>
          <section className="panel-card compare-results">
            <div className="panel-heading">
              <div>
                <p className="eyebrow">RANKING SNAPSHOT COMPARISON</p>
                <h2>Same poule, same season.</h2>
              </div>
              <span className="cohort-count">
                <Users size={14} />
                {cohort.length} recorded players in this poule
              </span>
            </div>
            {cohortMedian !== null && (
              <div className="cohort-benchmark">
                <span className="benchmark-icon"><Activity size={15} /></span>
                <p>
                  Poule median win rate <strong>{formatRate(cohortMedian)}</strong>
                  <small>Derived from {cohortRates.length} non-null source snapshots; not an official rank.</small>
                </p>
              </div>
            )}
            <div className="comparison-table">
              <div className="comparison-table-head">
                <span>PLAYER</span>
                <span>TEAM</span>
                <span>PLAYED</span>
                <span>WINS</span>
                <span>WIN RATE VS MEDIAN</span>
                <span>RATING</span>
              </div>
              {rows.map(({ player, appearance, name }) => {
                const pct = appearance.ranking.win_pct
                const width = pct === null ? 0 : Math.max(0, Math.min(100, pct))
                return (
                  <div className="comparison-row" key={player.player_id}>
                    <span className="comparison-player">
                      <span className="mini-avatar">{initials(name)}</span>
                      <span>
                        <strong>{name}</strong>
                        <small>ID {player.player_id}</small>
                      </span>
                    </span>
                    <span>{appearance.team?.name ?? 'Unknown'}</span>
                    <span>{formatCount(appearance.ranking.played)}</span>
                    <span>{formatCount(appearance.ranking.wins)}</span>
                    <span className="comparison-rate-cell">
                      <span className="rate-number">{formatRate(pct)}</span>
                      <span
                        aria-label={
                          pct === null
                            ? 'Win rate not recorded'
                            : `Win rate ${formatRate(pct)}; poule median ${formatRate(cohortMedian)}`
                        }
                        className="comparison-meter"
                      >
                        <span className="comparison-meter-fill" style={{ width: `${width}%` }} />
                        {cohortMedian !== null && (
                          <span
                            className="comparison-median-mark"
                            style={{ left: `${cohortMedian}%` }}
                          />
                        )}
                      </span>
                    </span>
                    <span>{formatRating(appearance.ranking.rating)}</span>
                  </div>
                )
              })}
            </div>
            <p className="comparison-footnote">
              A ranking appearance is not an individual match result. Null
              ratings and percentages are left unfilled.
            </p>
          </section>
        </>
      )}
    </div>
  )
}

export default App
