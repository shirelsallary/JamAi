# JAM AI — Queue DNA Agent: Full Specification

## Context (read this first)
Before writing any code, read the following existing files to understand the current structure:
- `jam-ai-backend/app/services/queue_optimizer.py`
- `jam-ai-backend/app/services/session_service.py`
- `jam-ai-backend/app/services/debounce_service.py`
- `jam-ai-backend/app/services/platform_factory.py`
- `jam-ai-backend/app/adapters/spotify_adapter.py` and `youtube_adapter.py`
- `jam-ai-backend/app/models/models.py`
- `jam-ai-backend/app/routers/sessions.py`, `queue.py`

**The existing engine (`build_scored_recommendations` in `queue_optimizer.py`) does not meet the project's requirements and must be fully replaced by the new engine described below — not extended, replaced.**

Known issues the new engine must fix (from a prior architectural audit):
1. `Session.context_vector` (genre/mood/language/time) is saved to the DB but is never loaded or taken into account when building the queue.
2. The current engine only scans top-tracks/top-artists ("most played"), never the user's saved/library playlists.
3. There is no quality threshold at all — every track found is added to the queue.
4. There is no fallback/expansion to public playlists when personal matches run out.
5. `register_user` sets a false default `platform="spotify"` even for users who never connected any account — this must be fixed so a user with no connected platform doesn't silently "impersonate" an empty Spotify account, and instead gets a clear message.
6. There is currently no screen/field where the host or a guest chooses which platform (Spotify / YouTube Music) to use **for this specific session** — even if the user has both connected. This must be added on both backend and frontend (see new Section 0).

---

## Exact Functional Specification

### 0. Independent platform selection per participant (new — takes precedence over everything else)
**Principle:** Every user (host or guest) chooses, at JAM creation time or at join time, **which of their own connected platforms** (Spotify and/or YouTube Music, whichever they've connected) they want to participate with — **with no dependency at all** on the host's choice or on other participants. Reason: guests only contribute data (playlist scanning) for building the queue — they do **not** need an account on the same platform as the host, because actual playback always runs only through the host's account (FR-4, Technical Design §5 "Host-side only").

**Data model changes:**
- `sessions.host_platform: str` — set explicitly at session creation, chosen from the platforms the host has actually connected (not a default, not inferred from `users.platform`). This is the field that determines which Adapter actually controls playback.
- `session_participants.selected_platform: str` — set at join time, from the platforms that specific participant has connected. It does **not** need to match `host_platform`.

**Backend (API) changes:**
- `POST /sessions` now accepts an additional required field `host_platform` in the request body — the server must verify the host actually has this platform connected (`users.connected_platforms` — see Section 8 for the related model expansion), otherwise return 400 with a clear message.
- `GET /sessions/{id}/join` (or POST, per the existing implementation) now accepts a required field `selected_platform` — same kind of validation: if the guest hasn't connected the platform they chose, return 400 ("Connect {platform} first").
- There is **no** validation requiring `selected_platform` to equal `host_platform` — this is exactly the point that changed from the earlier design.

**Frontend changes:**
- `CreateSessionScreen` — add a step before session creation: selection buttons "Play via Spotify" / "Play via YouTube Music", showing **only** the platforms the host has actually connected (if they only connected Spotify, don't show a YouTube button at all).
- `JoinSessionScreen` — add a similar step: "Which platform would you like to join with?", again limited to platforms that specific guest has connected. There is no dependency on the host's platform — there's no need to show `host_platform` to the guest at this stage at all.
- If a user (host or guest) has only one platform connected — skip the selection screen and auto-select it (don't force an unnecessary choice when there's no real decision to make).

**Important implication for the rest of the engine (see Sections 2.5, 2.6, 3, 4, 5 below):** Because different participants can now be on different platforms, there is a new problem of **cross-platform track/artist identification** (the same song, two different track_ids) — this is solved in Sections 2.5 (normalized comparison) and 2.6 (resolving a track for the host's platform).

### 1. Session DNA — building the target vector
When a session is created, build a `SessionDNA` object from the `context_vector` (genre, mood, language, time):

```
SessionDNA:
  target_valence: float (0.0-1.0)
  target_energy: float (0.0-1.0)
  target_genres: List[str]        # from the chosen genre + an expansion mapping (e.g. "Hip-Hop" -> ["hip-hop","rap","trap"])
  target_language: Optional[str]  # from the chosen language
  time_of_day: str                # kept for a future bonus/penalty use
```

Define a constants file `mood_to_audio_features.py`:
```python
MOOD_AUDIO_MAP = {
    "Energetic": {"valence": 0.8, "energy": 0.85},
    "Chill":     {"valence": 0.5, "energy": 0.25},
    "Happy":     {"valence": 0.9, "energy": 0.65},
    # ... complete this for every possible value in the Guided Contextual Input screen (FR-3)
}
TIME_ENERGY_ADJUSTMENT = {
    "Morning": +0.05, "Night": -0.05, "Late Night": -0.15, "Day": 0.0,
}
```
Final `target_energy` = the mood's value + the adjustment from `time_of_day`, clamped to [0,1].

Store `SessionDNA` as a new JSONB column on the `sessions` table (`session_dna`, derived automatically from `context_vector` at session-creation time) — so it is not recomputed on every run.

### 2. Computing a match score for a single track
Create a function `compute_match_score(track_features: TrackFeatures, dna: SessionDNA) -> float` that returns a value between 0.0 and 1.0:

```
audio_distance = sqrt((track.valence - dna.target_valence)^2 + (track.energy - dna.target_energy)^2) / sqrt(2)
audio_score = 1 - audio_distance                      # 0..1, closer = higher

genre_overlap = |track.genres ∩ dna.target_genres| / max(1, |dna.target_genres|)   # 0..1

language_bonus = 0.1 if track.detected_language == dna.target_language else 0.0

raw_score = (0.5 * audio_score) + (0.4 * genre_overlap) + language_bonus
final_score = min(1.0, raw_score)
```
Document the weights (0.5 / 0.4 / 0.1) as named constants at the top of the file so they're easy to tune later.

**Note on YouTube:** ytmusicapi has no audio features (valence/energy) like Spotify does. In that case `audio_score` must be computed purely from genre + textual metadata matching (title/album tags, if available), and it must be clearly documented in code that YouTube tracks get a lower-confidence score — add a `confidence: "high"|"low"` field to every score; YouTube tracks without audio features get `"low"`.

### 2.5 Social prioritization — playlist overlap and shared artists
Among the tracks that already passed the match threshold (Section 4), prioritize by social overlap **before** the match itself — this is a hierarchical (lexicographic) sort, not a numeric bonus mixed into `match_score`.

**Important — since participants can now be on different platforms (Section 0), raw `track_id`/`artist_id` values cannot be compared across Spotify and YouTube — these are two entirely separate ID spaces.** Comparison must use a **normalized key** built from title + artist:

```python
def normalize_key(title: str, artist: str) -> str:
    # lowercase, strip punctuation, strip common suffixes like "(feat. ...)", "official video", "remastered"
    t = strip_noise_suffixes(title.lower().strip())
    a = strip_noise_suffixes(artist.lower().strip())
    return f"{t}::{a}"

def compute_social_overlap(track, all_participants_saved_playlists) -> tuple[int, int]:
    track_key = normalize_key(track.title, track.primary_artist)
    artist_key = normalize_key("", track.primary_artist)

    playlist_overlap_count = len({
        p.id for p in all_participants_saved_playlists
        if track_key in p.normalized_track_keys   # normalized comparison, platform-independent
    })
    shared_artist_count = len({
        p.id for p in all_participants_saved_playlists
        if artist_key in p.normalized_artist_keys
    })
    return playlist_overlap_count, shared_artist_count
```
Every scanned participant (Section 3) must, in addition to the raw data, also store normalized sets: `normalized_track_keys` and `normalized_artist_keys` — so the overlap comparison works across platforms. Document in the README/code that this is a fuzzy-text match (not a guaranteed unique identifier) — rare false positives/negatives are possible (e.g. remixes with an almost-identical name).

**Final queue sort order (within the same "threshold tier" from the descending ladder in Section 4):**
```python
sort_key = lambda track: (
    -track.playlist_overlap_count,   # 1. how many participants overlap on the exact playlist — most important
    -track.shared_artist_count,      # 2. how many participants share the artist
    -track.match_score,              # 3. the DNA match — final tie-breaker only
)
```
**Critical clarification:** overlap does **not** change `match_score` itself and does not affect which "threshold tier" (80%/75%/70%...) a track belongs to — a track with high overlap but too low a match_score is **not** "pushed up" into a higher tier. The social sort applies **only within** the group of tracks that already passed the same threshold. In other words, the overall priority order is: (1) meeting the match threshold → (2) playlist overlap → (3) shared artists → (4) raw match_score.

Compute `playlist_overlap_count` and `shared_artist_count` once while building the candidate pool, and store them as fields on the row in `session_candidate_tracks` (do not recompute on every re-rank/skip — this is part of the same principle as Section 6, "Skip with no API calls / heavy recomputation").

When a new guest joins (Section 5), update `playlist_overlap_count`/`shared_artist_count` **only** for tracks that exist in the new guest's playlists (a targeted increment), not a full recomputation across the whole candidate pool.

### 2.6 Cross-platform resolution — turning a track into something playable on the host's platform
Since actual playback runs **only** through the host's platform (`session.host_platform`), any track discovered via a participant on a **different** platform than `host_platform` (e.g. a guest on YouTube, host on Spotify) must go through a "resolution" step before it's actually added to the queue — it cannot "play" using its original track_id on a platform it doesn't exist on.

```python
RESOLUTION_MATCH_THRESHOLD = 0.85   # fuzzy text-similarity threshold to accept a track as "the same song"

def resolve_track_for_host_platform(candidate_track, host_platform: str, host_adapter) -> Optional[Track]:
    if candidate_track.platform == host_platform:
        return candidate_track   # no resolution needed — already on the same platform

    query = f"{candidate_track.title} {candidate_track.primary_artist}"
    results = host_adapter.search_tracks(query, limit=3)   # add search_tracks to the adapter if missing
    best = pick_best_fuzzy_match(results, candidate_track, threshold=RESOLUTION_MATCH_THRESHOLD)

    if best is None:
        log.info(f"track '{candidate_track.title}' by {candidate_track.primary_artist} "
                 f"could not be resolved on {host_platform} — excluded from queue")
        return None

    # If the host is on Spotify and the original track came from YouTube (no audio features) —
    # after resolution, fetch real audio features from Spotify and upgrade confidence to "high",
    # and optionally recompute match_score with the more accurate data.
    if host_platform == "spotify" and candidate_track.confidence == "low":
        best.audio_features = host_adapter.get_audio_features(best.track_id)
        best.confidence = "high"

    return best
```
**Where this happens in the flow:** after the final sort (end of `build_initial_queue`, before actually writing to `queue_tracks`) — not earlier, so as not to waste search calls on tracks that wouldn't pass the match threshold/social sort anyway.

**What happens if resolution fails for some tracks:** if a non-trivial fraction of the selected tracks can't be found on `host_platform` (e.g. a niche song that only exists on YouTube), the final queue will be smaller than the target. In that case — as in Section 4 — mark `queue_build_status = "partial"` if the final result (after resolution) is smaller than `target_queue_size(session)`, and do not try to backfill with tracks below the original match threshold just to "hit a number."

### 3. Collecting candidates — saved playlists (not top-tracks!)
Add new adapter methods (if they don't already exist):
- Spotify: `get_user_playlists()` → `GET /me/playlists`, then for each playlist `get_playlist_tracks(playlist_id)` → `GET /playlists/{id}/tracks`.
- YouTube: `get_user_playlists()` → `ytmusicapi.get_library_playlists()`, then `get_playlist_tracks(playlist_id)` → `ytmusicapi.get_playlist(playlist_id)`.

For every track collected, fetch audio features (Spotify: `get_audio_features` in batches; YouTube: not available, see Section 2).

**Platform decision (updated — see Section 0):** scan each participant's playlists **on the platform they themselves selected** (`session_participants.selected_platform`) — **not necessarily** the host's platform. There is no skipping of participants who don't match the host's platform — every participant is always scanned, as long as they connected the platform they chose at join time (already guaranteed by the Section 0 validation). Result: a single candidate pool can contain tracks from both platforms at once — which is why the overlap (2.5) and resolution (2.6) steps downstream are mandatory.

### 4. The scanning algorithm with a descending threshold
```
THRESHOLD_LADDER = [0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50]   # floor: 0.50, must never go below this
MAX_PUBLIC_SEARCH_QUERIES = 5     # API call budget for public search, to prevent rate-limiting

def build_initial_queue(session) -> List[ScoredTrack]:
    dna = load_or_build_session_dna(session)
    candidates = []
    for participant in session.participants:
        candidates += scan_saved_playlists(participant, participant.selected_platform)   # the participant's own platform, not the host's
    scored = [ (track, compute_match_score(track, dna)) for track in dedupe(candidates) ]

    accepted = []
    for threshold in THRESHOLD_LADDER:
        accepted = [t for t,s in scored if s >= threshold]
        if len(accepted) >= target_queue_size(session):
            break
    else:
        # didn't reach a sufficient amount even at 0.50 — chain to a public search (host platform only, see note below)
        accepted += chain_public_playlist_search(dna, session.host_platform,
                                                   already_have=accepted,
                                                   min_threshold=0.50,
                                                   max_queries=MAX_PUBLIC_SEARCH_QUERIES)

    with_overlap = [attach_social_overlap(t, session.participants) for t in accepted]
    ranked = sorted(with_overlap, key=lambda t: (-t.playlist_overlap_count, -t.shared_artist_count, -t.match_score))

    # final step: resolve every track whose source platform differs from host_platform (Section 2.6) — only here, after the final sort
    host_adapter = get_platform_adapter(session.host_platform)
    resolved = [resolve_track_for_host_platform(t, session.host_platform, host_adapter) for t in ranked]
    return [t for t in resolved if t is not None]
```
(See Section 2.5 for `attach_social_overlap` and the exact hierarchical sort key, and Section 2.6 for `resolve_track_for_host_platform`.)

**Note:** `chain_public_playlist_search` always searches on the host's platform only (`session.host_platform`) — there's no point searching public playlists on a different platform and then having to "resolve" them anyway; better to save the unnecessary API calls.

`target_queue_size(session)`: if a target duration was set (FR-6, playlist-creation screen) — compute it from the average track length (~3.5 minutes); otherwise use a reasonable default (e.g. 25 tracks).

`chain_public_playlist_search`:
1. Build keywords from the DNA: `f"{genre} {mood} {language}"` plus partial combinations (genre+mood only, mood only).
2. Search for public playlists on the platform (Spotify: `GET /search?type=playlist`; YouTube: `ytmusicapi.search(query, filter="playlists")`).
3. For each playlist in the results (capped at `max_queries` calls total) — fetch tracks, score them against the DNA, keep those above `min_threshold`.
4. Stop early once `target_queue_size` is reached.
5. If after `max_queries` the target amount still hasn't been reached — **do not fail silently**. Mark `session.queue_build_status = "partial"` and return whatever was found (even if smaller than the target). This must be visible to the frontend (see Section 7).

### 5. Updating the queue when a new guest joins (not a full re-run!)
When a new `SessionParticipant` is created (guest join):
```
def on_guest_joined(session, new_participant):
    dna = session.session_dna   # already exists, not rebuilt
    new_candidates = scan_saved_playlists(new_participant, new_participant.selected_platform)   # the platform the guest themselves chose
    new_scored = [(t, compute_match_score(t, dna)) for t in new_candidates]
    new_accepted = [t for t,s in new_scored if s >= current_effective_threshold(session)]
    update_social_overlap_incremental(session, new_participant, new_accepted)  # see Section 2.5 — targeted update only
    resolved = [resolve_track_for_host_platform(t, session.host_platform, get_platform_adapter(session.host_platform))
                for t in new_accepted]
    merge_into_queue(session, [t for t in resolved if t is not None])   # add to the existing pool + re-sort by the hierarchical sort key
```
**Do not** call `scan_saved_playlists` again on participants who were already scanned. Store the candidate pool (a ranked pool of candidates, including ones that didn't pass the threshold) in a cache (a new table `session_candidate_tracks`, or Redis) for reuse.

### 6. Skip — re-rank only, no API calls
`PATCH /queue/{id}/skip` must work **only** against the stored candidate pool (from the DB/cache), **with no external HTTP calls whatsoever**. This is critical for meeting NFR-1 (3 seconds), which previously failed in test TC-7.

**Protecting the currently playing track:** before any re-rank/rebuild, ensure the track currently at `position=0` and marked as "currently playing" is not replaced unless it is the one being skipped.

### 7. User-facing transparency (frontend)
Add a `queue_build_status: "full" | "partial" | "empty"` field plus `effective_threshold: float` to the `GET /queue/{session_id}` response. On the frontend, if the status is `"partial"` or `"empty"` — show the user a message (e.g. "We found expanded matches (65%) because there aren't enough songs in the connected playlists") instead of a silent empty screen. This directly fixes the "empty screen with no error message" bug documented in the prior audit.

### 8. Related fix — false default platform
Fix `register_user` so that `users.platform` is nullable (or has a `"none"` value) until the user actually completes OAuth. `get_platform_adapter` should throw a clear error (`NoPlatformConnectedError`) when there's no valid token, instead of returning a `SpotifyAdapter(token="")` that fails silently.

---

## Testing Requirements (must be written before declaring the work done)

Write pytest tests for all of the following, with mocks for the Spotify/YouTube adapters (do not make real network calls in tests):

1. **`test_session_dna_construction`** — given various context_vectors (covering every mood value in the mapping), the resulting `SessionDNA` matches the expected values (including the time adjustment).
2. **`test_match_score_formula`** — parametrized tests: a track identical to the DNA → score close to 1.0; a fully opposite track (inverted valence/energy, no genre overlap) → score close to 0.0; a dedicated test confirming YouTube tracks with no audio features get `confidence="low"`.
3. **`test_threshold_ladder_degradation`** — simulate a situation where only tracks scoring 0.62 exist — verify the algorithm descends the ladder and stops at the correct threshold (0.60), and never drops below 0.50 even if there still aren't enough tracks.
4. **`test_public_search_chaining_respects_query_budget`** — verify `chain_public_playlist_search` never exceeds `MAX_PUBLIC_SEARCH_QUERIES` calls, even when there are many potential results.
5. **`test_partial_status_when_insufficient_matches`** — when even after public search there still aren't enough tracks, verify `queue_build_status == "partial"` and that all tracks that WERE found are still returned (not an empty queue when at least one valid track exists).
6. **`test_guest_join_does_not_rescan_existing_participants`** — mock `scan_saved_playlists`, verify that on a new guest joining, the function is called exactly once (for the new guest only), never for existing participants.
7. **`test_skip_never_calls_external_api`** — a mock verifying the skip endpoint never calls any adapter method that reaches the network (only the candidate pool from the DB).
8. **`test_currently_playing_track_protected_on_reorder`** — verify a track at position 0 marked "currently playing" doesn't move during a re-rank when it isn't the one being skipped.
9. **`test_participant_scanned_on_own_selected_platform`** — host on Spotify, guest chose YouTube as `selected_platform`: verify the guest is scanned via YouTube (not skipped/failed for not matching the host).
9a. **`test_join_requires_selected_platform_connected`** — attempting to join with `selected_platform="youtube"` when the user has no YouTube account connected at all → 400 with a clear message.
9b. **`test_cross_platform_track_resolution_success`** — a track found via a YouTube guest, `host_platform="spotify"`: mock `search_tracks` returning a matching result (fuzzy score above 0.85) → the returned track has Spotify's `track_id`/`platform`, and `confidence` upgraded to `"high"`.
9c. **`test_cross_platform_track_resolution_failure_excludes_track`** — same scenario, but `search_tracks` returns nothing passing `RESOLUTION_MATCH_THRESHOLD` → the track resolves to `None` and does not appear in the final queue, with a clear log entry.
9d. **`test_social_overlap_uses_normalized_key_across_platforms`** — two participants, one with the song on Spotify (title="Song A", artist="X") and the other with the same song on YouTube (title="Song A", artist="X", a completely different track_id) → `playlist_overlap_count` counts both as an overlap (via `normalize_key`, not `track_id`).
10. **`test_social_overlap_beats_higher_match_score`** — two tracks in the same threshold tier (e.g. both passed 70%): track A with `match_score=0.95` and `playlist_overlap_count=0`, track B with `match_score=0.71` and `playlist_overlap_count=3`. Verify track B appears before track A in the queue (the hierarchical sort, not a numeric bonus).
11. **`test_shared_artist_tiebreak_below_playlist_overlap`** — two tracks with the same `playlist_overlap_count`: verify the tie-break falls to `shared_artist_count`, and only if that's also equal — to `match_score`.
12. **`test_overlap_does_not_promote_track_across_threshold_tiers`** — a track with `match_score=0.55` (below the 0.60 threshold that was actually reached) but a very high `playlist_overlap_count` — verify the track does **not** enter the queue at all, because overlap doesn't affect membership in the threshold tier itself.
13. **`test_incremental_overlap_update_on_guest_join`** — a mock verifying that when a new guest joins, `playlist_overlap_count`/`shared_artist_count` are updated only for tracks that exist in the new guest's playlists, and are not recomputed for the entire candidate pool.
14. **`test_no_silent_fake_platform_default`** — verify `register_user` never sets `platform="spotify"` as a default, and that trying to use an adapter with no real connection throws `NoPlatformConnectedError` instead of failing silently.

Additionally — write one end-to-end integration test (`test_full_session_lifecycle`): create session → build DNA → initial queue → guest joins → merge → skip → verify the queue at every stage matches the expectations from the spec above.

## Required Output When Done
1. Fully implemented code (not a theoretical PR) with all tests passing (full `pytest -v` output).
2. A short summary: which files were created/modified, and which DB migrations are required (new columns/tables).
3. A list of every assumption you had to make (e.g. if information about a specific API's exact response shape was missing) — do not stay silent about gaps, document them explicitly.
