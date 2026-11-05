import { useState, useEffect, useRef } from 'react'

// Unsplash image IDs
const IMG_TIMES_SQUARE_CROWD = 'https://images.unsplash.com/photo-1601751664209-be452817a8ce?w=800&h=1400&fit=crop&auto=format'
const IMG_TIMES_SQUARE_WIDE = 'https://images.unsplash.com/photo-1571182104827-35bb8095b959?w=800&h=1200&fit=crop&auto=format'
const IMG_TIMES_SQUARE_SIGNS = 'https://images.unsplash.com/photo-1552519837-47846308a0e9?w=800&h=1400&fit=crop&auto=format'
const IMG_TIMES_SQUARE_NIGHT = 'https://images.unsplash.com/photo-1503640838962-d3d3cadf1847?w=800&h=1400&fit=crop&auto=format'
const IMG_CITY_BOKEH = 'https://images.unsplash.com/photo-1542902093-d55926049754?w=800&h=1200&fit=crop&auto=format'
const IMG_NEON_STREET = 'https://images.unsplash.com/photo-1608690158878-1a96b29b455b?w=800&h=1400&fit=crop&auto=format'

// Alpine images for the Start a Story / TMB flow
const IMG_ALPS_PANORAMA   = 'https://images.unsplash.com/photo-1506905925346-21bda4d32df4?w=800&h=1200&fit=crop&auto=format'
const IMG_MOUNTAIN_TRAIL  = 'https://images.unsplash.com/photo-1464822759023-fed622ff2c3b?w=800&h=1400&fit=crop&auto=format'
const IMG_MOUNTAIN_LAKE   = 'https://images.unsplash.com/photo-1531366936337-7c912a4589a7?w=800&h=1400&fit=crop&auto=format'
const IMG_MOUNTAIN_HIKERS = 'https://images.unsplash.com/photo-1454496522488-7a8e488e8606?w=800&h=1200&fit=crop&auto=format'
const IMG_MOUNTAIN_RIDGE  = 'https://images.unsplash.com/photo-1502786129293-79981df4e689?w=800&h=1400&fit=crop&auto=format'
const IMG_MOUNTAIN_MIST   = 'https://images.unsplash.com/photo-1558618666-fcd25c85cd64?w=800&h=1200&fit=crop&auto=format'
const IMG_COUPLE_HIKING   = 'https://images.unsplash.com/photo-1521804906057-1df8fdb718b7?w=800&h=1400&fit=crop&auto=format'

// Mosaic images used for the TMB Story home
const TMB_MOSAIC = [IMG_ALPS_PANORAMA, IMG_MOUNTAIN_TRAIL, IMG_MOUNTAIN_LAKE, IMG_MOUNTAIN_HIKERS, IMG_MOUNTAIN_RIDGE, IMG_MOUNTAIN_MIST]

// Story arc chapters for the TMB Blueprint screen
const TMB_CHAPTERS = [
  { name: 'Departure',          note: 'leaving for something big'              },
  { name: 'On the Trail',       note: 'day after day, moving through'          },
  { name: 'Scale',              note: 'the mountains as they actually are'     },
  { name: 'The People in It',   note: 'who you are out there'                  },
  { name: 'Effort',             note: 'what the trail actually asks'           },
  { name: 'Arriving',           note: 'the feeling of completing it'           },
]

// Story Guide — the persistent, richer counterpart of the arc above.
// These categories are generated PER STORY. They are specific to this hiking
// journey and must NOT be reused for weddings, concerts, road trips, etc.
// Advisory only — never a checklist, count, or requirement.
type GuideTone = 'covered' | 'strong' | 'more' | 'later'
type GuideShot = { title: string; concept: string; note: string }
type GuideItem = {
  label: string
  captured: boolean   // whether the Story already has this moment
  shot: GuideShot     // the guidance shown when the user shoots it directly
}
type GuideCategory = {
  id: string
  title: string
  intent: string
  state: string
  tone: GuideTone
  items: GuideItem[]
}
// What the shoot flow receives when launched from a specific guide moment.
type ShootGuide = { category: string; shot: GuideShot }
const TMB_STORY_GUIDE: GuideCategory[] = [
  {
    id: 'opening',
    title: 'Opening',
    intent: 'Establish where the journey begins.',
    state: "You've got this covered",
    tone: 'covered',
    items: [
      { label: 'Packing — boots, backpack', captured: true, shot: { title: 'The Gear by the Door', concept: 'Frame your boots and packed backpack by the door before you set out. Let the gear tell the story of departure.', note: '6 sec · Establishes the departure.' } },
      { label: 'Leaving the hotel', captured: true, shot: { title: 'Stepping Out', concept: 'Film the moment you walk out and the trail opens up ahead of you.', note: '6 sec · Marks the start.' } },
      { label: 'First reveal of the mountains', captured: true, shot: { title: 'First Sight', concept: 'Hold on the first time the mountains come into full view. Let the reveal breathe.', note: '8 sec · The journey becomes real.' } },
    ],
  },
  {
    id: 'journey',
    title: 'Journey',
    intent: 'Show movement through the Alps.',
    state: 'Looking strong',
    tone: 'strong',
    items: [
      { label: 'Walking away from camera', captured: true, shot: { title: 'Into the Trail', concept: 'Set the camera down and walk away along the path. Let the trail lead the eye into the mountains.', note: '8 sec · Shows the rhythm of the journey.' } },
      { label: 'Side profile on the trail', captured: true, shot: { title: 'Alongside', concept: 'Capture a side profile moving steadily across the frame.', note: '6 sec · Motion with the landscape behind.' } },
      { label: 'Boots moving through terrain', captured: false, shot: { title: 'Step by Step', concept: 'A low, close shot of boots crossing rock, root, and dirt.', note: '5 sec · The texture of the trail.' } },
    ],
  },
  {
    id: 'scale',
    title: 'Scale',
    intent: 'Make the mountains feel enormous.',
    state: 'Looking strong',
    tone: 'strong',
    items: [
      { label: 'A person beneath huge mountains', captured: true, shot: { title: 'Small Against It', concept: 'Place a person low in the frame with the mountains towering above.', note: '8 sec · Makes the peaks feel enormous.' } },
      { label: 'Wide landscape, person entering frame', captured: false, shot: { title: 'Entering the Vast', concept: 'Hold a wide landscape and let a person walk into the edge of the frame.', note: '8 sec · Scale through contrast.' } },
    ],
  },
  {
    id: 'human',
    title: 'Human moments',
    intent: 'Natural moments of both travelers.',
    state: 'Could use more',
    tone: 'more',
    items: [
      { label: 'Candid laughter at a rest stop', captured: false, shot: { title: 'A Shared Laugh', concept: "Catch an unposed laugh during a break — don't direct it, just be ready.", note: '6 sec · Human warmth.' } },
      { label: 'Sharing a view together', captured: false, shot: { title: 'Taking It In', concept: 'Film both of you looking out at the view, backs to camera.', note: '6 sec · A quiet moment together.' } },
      { label: 'A hand passing a water bottle', captured: false, shot: { title: 'Small Gestures', concept: 'Close on a small act of care — a hand passing a water bottle.', note: '5 sec · Intimacy in the detail.' } },
    ],
  },
  {
    id: 'challenge',
    title: 'Challenge',
    intent: 'Show that this was a real journey.',
    state: 'Could use more',
    tone: 'more',
    items: [
      { label: 'A steep uphill effort', captured: false, shot: { title: 'The Climb', concept: 'Film a steep push uphill — the effort in the legs and the pace.', note: '6 sec · Shows the real work.' } },
      { label: 'Catching your breath', captured: false, shot: { title: 'A Pause', concept: 'Capture a stop to breathe — hands on knees, the trail behind.', note: '5 sec · The cost of the climb.' } },
      { label: 'Crossing a rough section', captured: false, shot: { title: 'The Rough Bit', concept: 'Film a careful crossing of a rocky or exposed section.', note: '6 sec · Proves the terrain.' } },
    ],
  },
  {
    id: 'ending',
    title: 'Ending',
    intent: 'Give the Story closure.',
    state: 'Comes near the end',
    tone: 'later',
    items: [
      { label: 'The final ridge', captured: false, shot: { title: 'The Last Ridge', concept: 'Capture the final ridge line as it comes into view.', note: '8 sec · The end in sight.' } },
      { label: 'Looking back at the route', captured: false, shot: { title: 'Looking Back', concept: "Turn the camera to the route behind — how far you've come.", note: '8 sec · Reflection.' } },
      { label: 'Arriving where it ends', captured: false, shot: { title: 'Arriving', concept: 'Film the final steps into where the journey ends.', note: '8 sec · Closure.' } },
    ],
  },
]

// Advisory state colour — subtle, palette-safe. Gentle gold nudge for "more".
const guideToneColor: Record<GuideTone, string> = {
  covered: 'rgba(245,240,232,0.4)',
  strong:  'rgba(245,240,232,0.4)',
  more:    'rgba(212,168,83,0.75)',
  later:   'rgba(245,240,232,0.22)',
}

// Camera roll thumbnails for the media picker
const CAMERA_ROLL: Array<{ id: string; src: string; video: boolean }> = [
  { id: 'r1', src: 'https://images.unsplash.com/photo-1601751664209-be452817a8ce?w=300&h=400&fit=crop&auto=format', video: false },
  { id: 'r2', src: 'https://images.unsplash.com/photo-1519501025264-65ba15a82390?w=300&h=400&fit=crop&auto=format', video: false },
  { id: 'r3', src: 'https://images.unsplash.com/photo-1552519837-47846308a0e9?w=300&h=400&fit=crop&auto=format', video: true },
  { id: 'r4', src: 'https://images.unsplash.com/photo-1608690158878-1a96b29b455b?w=300&h=400&fit=crop&auto=format', video: false },
  { id: 'r5', src: 'https://images.unsplash.com/photo-1503640838962-d3d3cadf1847?w=300&h=400&fit=crop&auto=format', video: true },
  { id: 'r6', src: 'https://images.unsplash.com/photo-1534430480872-3498386e7856?w=300&h=400&fit=crop&auto=format', video: false },
  { id: 'r7', src: 'https://images.unsplash.com/photo-1477959858617-67f85cf4f1df?w=300&h=400&fit=crop&auto=format', video: false },
  { id: 'r8', src: 'https://images.unsplash.com/photo-1542902093-d55926049754?w=300&h=400&fit=crop&auto=format', video: true },
  { id: 'r9', src: 'https://images.unsplash.com/photo-1571182104827-35bb8095b959?w=300&h=400&fit=crop&auto=format', video: false },
]

// A Moment = one photo or video the Story is considering. "Remove from Story"
// only stops the Story from using it — it never touches the user's device.
type MomentMedia = { id: string; src: string; video: boolean }
const INITIAL_MOMENTS: MomentMedia[] = Array.from({ length: 18 }, (_, i) => ({
  id: `m${i}`,
  src: TMB_MOSAIC[i % TMB_MOSAIC.length],
  video: i % 4 === 2,
}))

type Screen =
  // ── Home ──────────────────────────────────────────────
  | 'home'
  // ── DIRECT v0.1 (frozen) ──────────────────────────────
  | 'intent'
  | 'scene'
  | 'thinking'
  | 'idea'
  | 'shot1'
  | 'capture1'
  | 'validation1'
  | 'shot2'
  | 'capture2'
  | 'moments'
  | 'premediapicker'
  | 'premediaanalysis'
  | 'premediaresulta'
  | 'premediaresultb'
  | 'premediaresultc'
  | 'finalshot'
  | 'creating'
  | 'result'
  // ── Start a Story ─────────────────────────────────────
  | 'storyintent'
  | 'storydirection'
  | 'storycontext'
  | 'storyblueprint'
  | 'storystart'
  // ── TMB Persistent Story ──────────────────────────────
  | 'tmb'
  | 'tmbshot'
  | 'tmbcapture'
  | 'tmbvalidated'
  | 'tmblooked'
  | 'tmbready'
  | 'tmbpreview'
  | 'tmbmusic'
  | 'tmbshootscene'
  | 'tmbshootthinking'
  | 'tmbshootidea'
  | 'tmbshootshot'
  | 'tmbshootcapture'

// Corner brackets for camera/viewfinder UI
function ViewfinderCorners({ color = 'rgba(255,255,255,0.5)' }: { color?: string }) {
  const s = 28
  const t = 2.5
  return (
    <>
      {[
        { top: 20, left: 20, borderTop: t, borderLeft: t, borderRight: 0, borderBottom: 0 },
        { top: 20, right: 20, borderTop: t, borderRight: t, borderLeft: 0, borderBottom: 0 },
        { bottom: 20, left: 20, borderBottom: t, borderLeft: t, borderRight: 0, borderTop: 0 },
        { bottom: 20, right: 20, borderBottom: t, borderRight: t, borderLeft: 0, borderTop: 0 },
      ].map((pos, i) => (
        <div
          key={i}
          style={{
            position: 'absolute',
            width: s,
            height: s,
            borderColor: color,
            borderStyle: 'solid',
            borderTopWidth: pos.borderTop || 0,
            borderLeftWidth: pos.borderLeft || 0,
            borderRightWidth: pos.borderRight || 0,
            borderBottomWidth: pos.borderBottom || 0,
            top: pos.top,
            left: pos.left,
            right: pos.right,
            bottom: pos.bottom,
          }}
        />
      ))}
    </>
  )
}

// Animated transition wrapper
function ScreenWrap({ children, active }: { children: React.ReactNode; active: boolean }) {
  const [mounted, setMounted] = useState(false)
  useEffect(() => {
    const t = setTimeout(() => setMounted(true), 10)
    return () => clearTimeout(t)
  }, [])
  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        opacity: active && mounted ? 1 : 0,
        transform: active && mounted ? 'translateY(0)' : 'translateY(12px)',
        transition: 'opacity 0.35s ease, transform 0.35s ease',
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
      }}
    >
      {children}
    </div>
  )
}

// ──────────────────────────────────────────────
// SCREEN 1 — Creative Intent
// ──────────────────────────────────────────────
const styleOptions = [
  {
    id: 'cinematic',
    label: 'Cinematic',
    img: IMG_TIMES_SQUARE_NIGHT,
    previewImg: IMG_TIMES_SQUARE_NIGHT,
    feel: 'Wide, moody, environment-first',
    examples: ['Long shot with lots of background', 'Slow, deliberate movement', 'Dramatic contrast'],
  },
  {
    id: 'energetic',
    label: 'Energetic',
    img: IMG_TIMES_SQUARE_CROWD,
    previewImg: IMG_TIMES_SQUARE_CROWD,
    feel: 'Fast, kinetic, in the moment',
    examples: ['Quick cuts between moments', 'Motion and movement', 'Close and immediate'],
  },
  {
    id: 'calm',
    label: 'Calm',
    img: IMG_CITY_BOKEH,
    previewImg: IMG_CITY_BOKEH,
    feel: 'Slow, quiet, reflective',
    examples: ['Soft backgrounds', 'Still or gently moving', 'Lots of breathing room'],
  },
  {
    id: 'playful',
    label: 'Playful',
    img: IMG_NEON_STREET,
    previewImg: IMG_NEON_STREET,
    feel: 'Bright, candid, full of life',
    examples: ['Colourful and spontaneous', 'Natural reactions', 'Fun over polished'],
  },
]

const refVibeTraits = ['Cinematic', 'Energetic', 'Person + scenery', 'Smooth movement']

// Per-vibe animation config for the simulated video preview
const vibeAnimConfig: Record<string, { animation: string; duration: string; opacity: number }> = {
  cinematic: { animation: 'kenBurnsCinematic', duration: '9s', opacity: 0.62 },
  energetic:  { animation: 'kenBurnsEnergetic', duration: '5s', opacity: 0.72 },
  calm:       { animation: 'kenBurnsCalm',      duration: '12s', opacity: 0.52 },
  playful:    { animation: 'kenBurnsPlayful',   duration: '7s', opacity: 0.68 },
}

// Looping progress bar that restarts every N seconds
function LoopBar({ duration }: { duration: number }) {
  const [key, setKey] = useState(0)
  useEffect(() => {
    const t = setInterval(() => setKey(k => k + 1), duration * 1000)
    return () => clearInterval(t)
  }, [duration])
  return (
    <div style={{ width: '100%', height: 2, background: 'rgba(255,255,255,0.15)', borderRadius: 2, overflow: 'hidden' }}>
      <div
        key={key}
        style={{
          height: '100%',
          background: 'rgba(245,240,232,0.8)',
          borderRadius: 2,
          animation: `loopProgress ${duration}s linear forwards`,
        }}
      />
    </div>
  )
}

type StyleOption = typeof styleOptions[number]

function VibePreviewOverlay({
  opt,
  visible,
  onClose,
  onConfirm,
}: {
  opt: StyleOption
  visible: boolean
  onClose: () => void
  onConfirm: (id: string) => void
}) {
  const anim = vibeAnimConfig[opt.id] ?? vibeAnimConfig.cinematic
  const loopSecs = parseFloat(anim.duration)

  return (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        zIndex: 50,
        background: '#0a0a0b',
        display: 'flex',
        flexDirection: 'column',
        opacity: visible ? 1 : 0,
        transition: 'opacity 0.28s ease',
        overflow: 'hidden',
      }}
    >
      {/* Simulated looping video — Ken Burns animated image */}
      <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
        <img
          src={opt.previewImg}
          alt={opt.label}
          style={{
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: anim.opacity,
            animation: `${anim.animation} ${anim.duration} ease-in-out infinite`,
            transformOrigin: 'center center',
          }}
        />
        {/* Gradient scrim */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,11,0.45) 0%, transparent 28%, rgba(10,10,11,0.6) 58%, #0a0a0b 100%)' }} />
      </div>

      {/* Top bar: back + looping badge */}
      <div style={{ position: 'relative', zIndex: 10, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '52px 20px 0' }}>
        <button
          onClick={onClose}
          style={{ background: 'rgba(10,10,11,0.4)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 50, width: 36, height: 36, display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer', color: '#f5f0e8', fontSize: 16 }}
        >
          ←
        </button>
        {/* Looping video indicator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, background: 'rgba(10,10,11,0.45)', backdropFilter: 'blur(8px)', border: '1px solid rgba(255,255,255,0.1)', borderRadius: 50, padding: '6px 12px' }}>
          <div style={{ width: 6, height: 6, borderRadius: '50%', background: '#d4a853', animation: 'fadeIn 0.5s ease' }} />
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.7)', letterSpacing: '0.08em' }}>Looping</span>
        </div>
      </div>

      {/* Bottom content */}
      <div style={{ position: 'relative', zIndex: 2, marginTop: 'auto', padding: '0 24px 36px' }}>
        {/* Loop progress bar */}
        <div style={{ marginBottom: 20 }}>
          <LoopBar duration={loopSecs} />
        </div>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.14em', color: 'rgba(245,240,232,0.35)', textTransform: 'uppercase', margin: '0 0 8px' }}>
          {opt.label}
        </p>
        <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 26, color: '#f5f0e8', margin: '0 0 16px', lineHeight: 1.25 }}>
          {opt.feel}
        </p>

        {/* Visual descriptors */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 7, marginBottom: 26 }}>
          {opt.examples.map((ex, i) => (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10, animation: `slideUp 0.3s ease ${i * 0.07}s both` }}>
              <div style={{ width: 4, height: 4, borderRadius: '50%', background: 'rgba(245,240,232,0.3)', flexShrink: 0 }} />
              <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.6)' }}>{ex}</span>
            </div>
          ))}
        </div>

        <button
          onClick={() => onConfirm(opt.id)}
          style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer' }}
        >
          Use this vibe
        </button>
      </div>
    </div>
  )
}

function Screen1Intent({ onNext, onBack, direction, onMusicChange }: {
  onNext: (vibe: string | null, description: string) => void
  onBack?: () => void
  direction: CreativeDirection
  onMusicChange: (m: MusicDirection) => void
}) {
  const [musicOpen, setMusicOpen] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [previewing, setPreviewing] = useState<string | null>(null)
  const [previewVisible, setPreviewVisible] = useState(false)
  const [desc, setDesc] = useState('')
  const [hasReference, setHasReference] = useState(false)
  const [vibeConfirmed, setVibeConfirmed] = useState(false)
  const [noticesExpanded, setNoticesExpanded] = useState(false)
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const openPreview = (id: string) => {
    setPreviewing(id)
    requestAnimationFrame(() => setPreviewVisible(true))
  }

  const closePreview = () => {
    setPreviewVisible(false)
    setTimeout(() => setPreviewing(null), 280)
  }

  const confirmPreview = (id: string) => {
    setSelected(id)
    closePreview()
  }

  const tapCard = (id: string) => {
    if (selected === id) {
      setSelected(null)
    } else {
      openPreview(id)
    }
  }

  const addReference = () => {
    setHasReference(true)
    setVibeConfirmed(false)
    setNoticesExpanded(false)
    if (!desc) setDesc('Less influencer-like. Show more of Times Square.')
    setTimeout(() => setVibeConfirmed(true), 700)
  }

  const removeReference = () => {
    setHasReference(false)
    setVibeConfirmed(false)
    setNoticesExpanded(false)
  }

  const previewOpt = styleOptions.find(o => o.id === previewing)

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes fadeIn { from { opacity: 0; } to { opacity: 1; } }
        @keyframes slideUp { from { opacity: 0; transform: translateY(16px); } to { opacity: 1; transform: translateY(0); } }
        @keyframes kenBurnsCinematic {
          0%   { transform: scale(1.08) translate(0%, 0%); }
          50%  { transform: scale(1.14) translate(-2%, -1.5%); }
          100% { transform: scale(1.08) translate(0%, 0%); }
        }
        @keyframes kenBurnsEnergetic {
          0%   { transform: scale(1.1) translate(0%, 0%); }
          25%  { transform: scale(1.18) translate(-3%, -2%); }
          50%  { transform: scale(1.12) translate(2%, -1%); }
          75%  { transform: scale(1.17) translate(-1%, 2%); }
          100% { transform: scale(1.1) translate(0%, 0%); }
        }
        @keyframes kenBurnsCalm {
          0%   { transform: scale(1.06) translate(0%, 0%); }
          50%  { transform: scale(1.10) translate(-1.5%, -1%); }
          100% { transform: scale(1.06) translate(0%, 0%); }
        }
        @keyframes kenBurnsPlayful {
          0%   { transform: scale(1.08) translate(0%, 0%); }
          33%  { transform: scale(1.13) translate(2%, -1.5%); }
          66%  { transform: scale(1.11) translate(-2%, 1%); }
          100% { transform: scale(1.08) translate(0%, 0%); }
        }
        @keyframes loopProgress {
          0%   { width: 0%; }
          100% { width: 100%; }
        }
      `}</style>

      {/* Template vibe preview — full-screen overlay inside the frame */}
      {previewing && previewOpt && (
        <VibePreviewOverlay
          opt={previewOpt}
          visible={previewVisible}
          onClose={closePreview}
          onConfirm={confirmPreview}
        />
      )}

      {/* Main scroll content */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '56px 24px 32px', background: '#0a0a0b', overflowY: 'auto' }}>
        {onBack && (
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.32)', padding: 0, marginBottom: 20, textAlign: 'left', alignSelf: 'flex-start' }}>← Back</button>
        )}
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.35)', textTransform: 'uppercase', marginBottom: 28 }}>Story</p>
        <h1 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 30, color: '#f5f0e8', lineHeight: 1.2, marginBottom: 6 }}>
          What do you want<br />to create?
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.38)', margin: '0 0 26px', lineHeight: 1.5 }}>
          Start anywhere. Add as much or as little as you want.
        </p>

        {/* Style grid — tap to preview, selected shows checkmark */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 16 }}>
          {styleOptions.map((opt) => {
            const isSelected = selected === opt.id
            return (
              <button
                key={opt.id}
                onClick={() => tapCard(opt.id)}
                style={{
                  position: 'relative',
                  borderRadius: 14,
                  overflow: 'hidden',
                  aspectRatio: '1 / 1.1',
                  border: isSelected ? '2px solid #d4a853' : '2px solid rgba(255,255,255,0.06)',
                  cursor: 'pointer',
                  transition: 'border-color 0.2s, opacity 0.2s',
                  background: '#1a1a1c',
                  opacity: selected && !isSelected ? 0.55 : 1,
                }}
              >
                <img
                  src={opt.img}
                  alt={opt.label}
                  style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: isSelected ? 0.75 : 0.4, transition: 'opacity 0.2s' }}
                />
                <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.85) 0%, transparent 55%)' }} />
                <div style={{ position: 'absolute', bottom: 10, left: 12, right: 12 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontWeight: 500, fontSize: 14, color: '#f5f0e8', margin: 0 }}>{opt.label}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.45)', margin: '3px 0 0' }}>{opt.feel}</p>
                </div>
                {isSelected && (
                  <div style={{ position: 'absolute', top: 9, right: 10, width: 18, height: 18, borderRadius: '50%', background: '#d4a853', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <span style={{ fontSize: 10, color: '#0a0a0b' }}>✓</span>
                  </div>
                )}
              </button>
            )
          })}
        </div>

        {/* Reference section */}
        {hasReference ? (
          <div style={{ marginBottom: 12 }}>
            {/* Compact reference card */}
            <div style={{
              borderRadius: 14,
              background: 'rgba(255,255,255,0.04)',
              border: '1.5px solid rgba(245,240,232,0.1)',
              overflow: 'hidden',
            }}>
              {/* Top row: thumbnail + header + controls */}
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '10px 12px' }}>
                <div style={{ width: 44, height: 56, borderRadius: 8, overflow: 'hidden', flexShrink: 0, background: '#1a1a1c', position: 'relative' }}>
                  <img src={IMG_TIMES_SQUARE_CROWD} alt="Reference" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.85 }} />
                  <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ width: 0, height: 0, borderTop: '5px solid transparent', borderBottom: '5px solid transparent', borderLeft: '8px solid rgba(245,240,232,0.85)' }} />
                  </div>
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#f5f0e8', margin: 0, fontWeight: 500, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>instagram_reel.mp4</p>
                  {vibeConfirmed ? (
                    <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontStyle: 'italic', fontWeight: 300, fontSize: 12, color: '#d4a853', margin: '3px 0 0', animation: 'fadeIn 0.4s ease' }}>
                      Got the vibe.
                    </p>
                  ) : (
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.3)', margin: '3px 0 0' }}>Reading it...</p>
                  )}
                </div>
                <div style={{ display: 'flex', gap: 12, flexShrink: 0 }}>
                  <button onClick={addReference} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.38)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, padding: 0 }}>Change</button>
                  <button onClick={removeReference} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.22)', fontFamily: "'DM Sans', sans-serif", fontSize: 12, padding: 0 }}>Remove</button>
                </div>
              </div>

              {/* Vibe traits + expand — only show after confirmed */}
              {vibeConfirmed && (
                <div style={{ borderTop: '1px solid rgba(245,240,232,0.07)', padding: '10px 12px 12px' }}>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6, marginBottom: noticesExpanded ? 0 : 6 }}>
                    {refVibeTraits.map((trait) => (
                      <span key={trait} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.55)', background: 'rgba(255,255,255,0.06)', borderRadius: 50, padding: '4px 10px' }}>
                        {trait}
                      </span>
                    ))}
                  </div>
                  {!noticesExpanded && (
                    <button
                      onClick={() => setNoticesExpanded(true)}
                      style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.35)', padding: '4px 0 0', textDecoration: 'underline', textDecorationColor: 'rgba(245,240,232,0.2)' }}
                    >
                      See what I noticed
                    </button>
                  )}
                  {noticesExpanded && (
                    <div style={{ marginTop: 10, animation: 'slideUp 0.25s ease' }}>
                      {[
                        { label: 'Pacing', value: 'Slow build, then reveal' },
                        { label: 'Framing', value: 'Person in a wide environment' },
                        { label: 'Feel', value: 'Natural, not staged' },
                        { label: 'Light', value: 'Night, ambient city glow' },
                      ].map(({ label, value }) => (
                        <div key={label} style={{ display: 'flex', justifyContent: 'space-between', padding: '5px 0', borderBottom: '1px solid rgba(245,240,232,0.05)' }}>
                          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.35)' }}>{label}</span>
                          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.6)' }}>{value}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}

              {/* "Anything you'd change?" — lives inside the card, below the vibe */}
              {vibeConfirmed && (
                <div style={{ padding: '0 12px 12px' }}>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.4)', margin: '8px 0 8px' }}>Anything you'd change?</p>
                  <textarea
                    value={desc}
                    onChange={(e) => setDesc(e.target.value)}
                    placeholder="e.g. Less influencer-like. Show more of Times Square."
                    style={{
                      width: '100%',
                      borderRadius: 10,
                      border: '1.5px solid rgba(245,240,232,0.1)',
                      background: 'rgba(255,255,255,0.04)',
                      color: '#f5f0e8',
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 13,
                      padding: '11px 13px',
                      resize: 'none',
                      height: 68,
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              )}
            </div>
          </div>
        ) : (
          <button
            onClick={addReference}
            style={{
              width: '100%',
              padding: '13px 20px',
              borderRadius: 14,
              border: '1.5px dashed rgba(245,240,232,0.13)',
              background: 'transparent',
              color: 'rgba(245,240,232,0.5)',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 14,
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: 10,
              marginBottom: 12,
              textAlign: 'left',
            }}
          >
            <span style={{ fontSize: 17, opacity: 0.6 }}>⊕</span>
            Show me something I like
          </button>
        )}

        {/* Free-text description — shown when no reference, or when reference hasn't loaded yet */}
        {!hasReference && (
          <textarea
            value={desc}
            onChange={(e) => setDesc(e.target.value)}
            placeholder="Or just describe what you want..."
            style={{
              width: '100%',
              borderRadius: 14,
              border: '1.5px solid rgba(245,240,232,0.1)',
              background: 'rgba(255,255,255,0.04)',
              color: '#f5f0e8',
              fontFamily: "'DM Sans', sans-serif",
              fontSize: 14,
              padding: '14px 16px',
              resize: 'none',
              height: 72,
              outline: 'none',
              boxSizing: 'border-box',
            }}
          />
        )}

        <div style={{ flex: 1 }} />

        {/* Music Direction — inferred live from the chosen vibe */}
        <div style={{ marginTop: 20 }}>
          <MusicDirectionRow
            direction={{ ...direction, tags: selected ? [styleOptions.find(o => o.id === selected)!.label] : direction.tags }}
            onChange={() => setMusicOpen(true)}
          />
        </div>

        <button
          onClick={() => onNext(selected, desc.trim())}
          style={{
            marginTop: 20,
            width: '100%',
            padding: '17px 0',
            borderRadius: 50,
            background: '#f5f0e8',
            color: '#0a0a0b',
            fontFamily: "'DM Sans', sans-serif",
            fontWeight: 600,
            fontSize: 15,
            border: 'none',
            cursor: 'pointer',
            letterSpacing: '0.02em',
          }}
        >
          Continue
        </button>

        {/* Secondary entry — existing media */}
        <button
          onClick={() => {/* placeholder — existing media workflow */}}
          style={{
            marginTop: 10,
            width: '100%',
            padding: '14px 0',
            borderRadius: 50,
            background: 'transparent',
            color: 'rgba(245,240,232,0.32)',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 14,
            border: 'none',
            cursor: 'pointer',
            letterSpacing: '0.01em',
          }}
        >
          + Add photos or videos
        </button>
      </div>
      {musicOpen && <MusicDirectionSheet direction={direction} onClose={() => setMusicOpen(false)} onSave={m => { onMusicChange(m); setMusicOpen(false) }} />}
    </ScreenWrap>
  )
}


// ──────────────────────────────────────────────
// SCREEN 3 — Show me where you are
// ──────────────────────────────────────────────
// Simulates a live camera viewfinder with animated scene capture.
// The camera fill dominates; text and controls are minimal overlays.

// Keyframes for the slow camera-pan simulation during capture
const SCENE_STYLE = `
  @keyframes scenePan {
    0%   { transform: scale(1.12) translate(0%,    0%); }
    30%  { transform: scale(1.18) translate(-2.5%, -1.5%); }
    65%  { transform: scale(1.15) translate(1.5%,  -2%); }
    100% { transform: scale(1.12) translate(0%,    0%); }
  }
  @keyframes sceneIdle {
    0%   { transform: scale(1.08) translate(0%, 0%); }
    50%  { transform: scale(1.10) translate(-1%, -0.5%); }
    100% { transform: scale(1.08) translate(0%, 0%); }
  }
  @keyframes captureRing {
    0%   { opacity: 0.6; transform: scale(1); }
    50%  { opacity: 1;   transform: scale(1.04); }
    100% { opacity: 0.6; transform: scale(1); }
  }
  @keyframes fadeInSlow { from { opacity: 0 } to { opacity: 1 } }
`

function Screen3Scene({ onNext, onBack }: { onNext: () => void; onBack?: () => void }) {
  const [phase, setPhase] = useState<'idle' | 'capturing' | 'done'>('idle')
  const [progress, setProgress] = useState(0)
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  // 4-second capture simulation
  const startCapture = () => {
    if (phase !== 'idle') return
    setPhase('capturing')
    const duration = 4000
    const tick = 50
    let elapsed = 0
    const interval = setInterval(() => {
      elapsed += tick
      setProgress(Math.min((elapsed / duration) * 100, 100))
      if (elapsed >= duration) {
        clearInterval(interval)
        setPhase('done')
        setTimeout(onNext, 700)
      }
    }, tick)
  }

  const circumference = 2 * Math.PI * 38 // radius 38 on a 88px svg

  return (
    <ScreenWrap active={active}>
      <style>{SCENE_STYLE}</style>

      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', overflow: 'hidden' }}>

        {/* ── Simulated camera feed ── */}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          <img
            src={IMG_TIMES_SQUARE_CROWD}
            alt=""
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              opacity: phase === 'idle' ? 0.5 : 0.65,
              transition: 'opacity 0.6s ease',
              animation: phase === 'capturing'
                ? 'scenePan 4s ease-in-out forwards'
                : 'sceneIdle 8s ease-in-out infinite',
              transformOrigin: 'center center',
            }}
          />
          {/* Exposure vignette */}
          <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 45%, transparent 38%, rgba(0,0,0,0.55) 100%)' }} />
          {/* Top and bottom scrim for text legibility */}
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,11,0.6) 0%, transparent 22%, transparent 62%, rgba(10,10,11,0.82) 100%)' }} />
        </div>

        {/* ── Viewfinder corners — only while idle ── */}
        {phase === 'idle' && <ViewfinderCorners color="rgba(245,240,232,0.25)" />}

        {/* ── Back button — visible only before scan starts ── */}
        {onBack && phase === 'idle' && (
          <button onClick={onBack} style={{ position: 'absolute', top: 50, left: 18, zIndex: 5, background: 'rgba(10,10,11,0.4)', backdropFilter: 'blur(6px)', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.45)', padding: '5px 12px', borderRadius: 50 }}>← Back</button>
        )}

        {/* ── Top label ── */}
        <div style={{ position: 'absolute', top: 52, left: 0, right: 0, textAlign: 'center', zIndex: 4, pointerEvents: 'none' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.3)', textTransform: 'uppercase', margin: 0 }}>Story</p>
        </div>

        {/* ── Primary text: shown only while idle ── */}
        {phase === 'idle' && (
          <div style={{ position: 'absolute', top: '17%', left: 0, right: 0, textAlign: 'center', zIndex: 4, padding: '0 32px', pointerEvents: 'none', animation: 'fadeInSlow 0.5s ease' }}>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 30, color: '#f5f0e8', margin: '0 0 10px', lineHeight: 1.2 }}>
              Show me<br />where you are.
            </h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.45)', margin: 0 }}>
              Slowly show me the scene.
            </p>
          </div>
        )}

        {/* ── Capturing: minimal in-progress hint ── */}
        {phase === 'capturing' && (
          <div style={{ position: 'absolute', top: '17%', left: 0, right: 0, textAlign: 'center', zIndex: 4, padding: '0 32px', pointerEvents: 'none', animation: 'fadeInSlow 0.3s ease' }}>
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 20, color: 'rgba(245,240,232,0.55)', margin: 0 }}>
              Keep going...
            </p>
          </div>
        )}

        {/* ── Bottom control area ── */}
        <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, zIndex: 4, display: 'flex', flexDirection: 'column', alignItems: 'center', paddingBottom: 48 }}>

          {/* Progress bar — appears during capture, fades in */}
          <div style={{
            width: 200,
            height: 2,
            borderRadius: 2,
            background: 'rgba(245,240,232,0.12)',
            marginBottom: 28,
            overflow: 'hidden',
            opacity: phase === 'capturing' ? 1 : 0,
            transition: 'opacity 0.3s',
          }}>
            <div style={{
              height: '100%',
              borderRadius: 2,
              background: 'rgba(245,240,232,0.7)',
              width: `${progress}%`,
              transition: 'width 0.05s linear',
            }} />
          </div>

          {/* Large capture button */}
          <div
            onClick={startCapture}
            style={{
              position: 'relative',
              width: 88,
              height: 88,
              cursor: phase === 'idle' ? 'pointer' : 'default',
            }}
          >
            {/* Animated SVG ring */}
            <svg
              width="88" height="88"
              style={{
                position: 'absolute',
                inset: 0,
                transform: 'rotate(-90deg)',
                animation: phase === 'capturing' ? 'captureRing 1.2s ease-in-out infinite' : 'none',
              }}
            >
              {/* Track */}
              <circle cx="44" cy="44" r="38" fill="none" stroke="rgba(245,240,232,0.15)" strokeWidth="2.5" />
              {/* Fill arc during capture */}
              {phase !== 'idle' && (
                <circle
                  cx="44" cy="44" r="38"
                  fill="none"
                  stroke={phase === 'done' ? '#d4a853' : 'rgba(245,240,232,0.8)'}
                  strokeWidth="2.5"
                  strokeDasharray={circumference}
                  strokeDashoffset={circumference * (1 - progress / 100)}
                  strokeLinecap="round"
                  style={{ transition: 'stroke-dashoffset 0.05s linear, stroke 0.3s' }}
                />
              )}
            </svg>

            {/* Inner button face */}
            <div style={{
              position: 'absolute',
              inset: 10,
              borderRadius: '50%',
              background: phase === 'done'
                ? '#d4a853'
                : phase === 'capturing'
                  ? 'rgba(245,240,232,0.12)'
                  : 'rgba(245,240,232,0.9)',
              transition: 'background 0.4s ease',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}>
              {phase === 'done' && (
                <span style={{ fontSize: 22, color: '#0a0a0b' }}>✓</span>
              )}
            </div>
          </div>

          {/* Instruction beneath button */}
          <p style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 13,
            color: 'rgba(245,240,232,0.35)',
            margin: '14px 0 0',
            letterSpacing: '0.02em',
            opacity: phase === 'capturing' ? 0 : 1,
            transition: 'opacity 0.3s',
          }}>
            {phase === 'idle' ? 'Tap to start' : ''}
          </p>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN 4 — Thinking
// ──────────────────────────────────────────────
function Screen4Thinking({ onNext }: { onNext: () => void }) {
  const [active, setActive] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(onNext, 3000)
    return () => clearTimeout(t)
  }, [onNext])

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes thinkPulse {
          0%, 100% { opacity: 0.15; transform: scale(0.85); }
          50%       { opacity: 0.7;  transform: scale(1.15); }
        }
        @keyframes thinkFadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes sceneFade {
          0%   { opacity: 0; }
          20%  { opacity: 1; }
          80%  { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>

      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>

        {/* Scene image fading behind — connects this state to what was just seen */}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          <img
            src={IMG_TIMES_SQUARE_CROWD}
            alt=""
            style={{
              width: '100%',
              height: '100%',
              objectFit: 'cover',
              animation: 'sceneFade 3s ease forwards',
            }}
          />
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.82)' }} />
        </div>

        {/* Centered content */}
        <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24, animation: 'thinkFadeIn 0.5s ease both' }}>
          {/* Three slow-breathing dots */}
          <div style={{ display: 'flex', gap: 9 }}>
            {[0, 1, 2].map((i) => (
              <div
                key={i}
                style={{
                  width: 6,
                  height: 6,
                  borderRadius: '50%',
                  background: '#f5f0e8',
                  animation: `thinkPulse 2s ease-in-out ${i * 0.32}s infinite`,
                }}
              />
            ))}
          </div>

          <p style={{
            fontFamily: "'Fraunces', Georgia, serif",
            fontWeight: 300,
            fontStyle: 'italic',
            fontSize: 24,
            color: 'rgba(245,240,232,0.65)',
            margin: 0,
            textAlign: 'center',
          }}>
            Looking for an idea...
          </p>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN 5 — Story Idea
// ──────────────────────────────────────────────
function Screen5Idea({ onNext, onAddExisting, onBack }: { onNext: () => void; onAddExisting: () => void; onBack?: () => void }) {
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0b', padding: '56px 24px 36px', overflowY: 'auto' }}>
        {onBack && (
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.32)', padding: 0, marginBottom: 18, textAlign: 'left', alignSelf: 'flex-start' }}>← Back</button>
        )}
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.35)', textTransform: 'uppercase', marginBottom: 20 }}>Story</p>
        <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 30, color: '#f5f0e8', margin: '0 0 4px' }}>I have an idea.</h2>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.3)', marginBottom: 28, letterSpacing: '0.08em', textTransform: 'uppercase' }}>Main Character</p>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 16, color: 'rgba(245,240,232,0.75)', lineHeight: 1.55, margin: '0 0 28px' }}>
          Move through the crowd, then reveal the city.
        </p>

        {/* Storyboard */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 24, flexShrink: 0 }}>
          {[
            { img: IMG_TIMES_SQUARE_CROWD, label: 'Shot 1', desc: 'Walk into the crowd' },
            { img: IMG_TIMES_SQUARE_WIDE, label: 'Shot 2', desc: 'Look up at the lights' },
          ].map((shot, i) => (
            <div key={i} style={{ flex: 1, borderRadius: 14, overflow: 'hidden', position: 'relative', aspectRatio: '9/14', background: '#1a1a1c' }}>
              <img src={shot.img} alt={shot.desc} style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.75) 0%, transparent 50%)' }} />
              <div style={{ position: 'absolute', bottom: 10, left: 10 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: '0 0 2px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{shot.label}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.6)', margin: 0 }}>{shot.desc}</p>
              </div>
              <div style={{ position: 'absolute', top: 8, left: 10, fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.4)' }}>{i + 1}</div>
            </div>
          ))}
        </div>

        {/* Metadata pill */}
        <div style={{ display: 'inline-flex', alignSelf: 'flex-start', padding: '7px 14px', borderRadius: 50, border: '1px solid rgba(245,240,232,0.12)', marginBottom: 28 }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.45)' }}>8 sec · 2 shots</span>
        </div>

        <div style={{ flex: 1 }} />

        {/* 1 — Primary */}
        <button
          onClick={onNext}
          style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 10 }}
        >
          Let's shoot
        </button>

        {/* 2 — Secondary: existing media */}
        <button
          onClick={onAddExisting}
          style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: 'transparent', color: 'rgba(245,240,232,0.55)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, border: '1.5px solid rgba(245,240,232,0.14)', cursor: 'pointer', marginBottom: 10 }}
        >
          + Add photos or videos
        </button>

        {/* 3 — Tertiary: no border, lowest weight */}
        <button
          style={{ width: '100%', padding: '13px 0', borderRadius: 50, background: 'transparent', color: 'rgba(245,240,232,0.28)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, border: 'none', cursor: 'pointer' }}
        >
          Try another idea
        </button>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// REUSABLE: Shot guidance screen
// ──────────────────────────────────────────────
// Visual example occupies the top ~62% of the screen.
// The image animates slowly to imply a looping video example.
// Text and button sit in a clean panel below.

const SHOT_STYLE = `
  @keyframes shotLoop1 {
    0%   { transform: scale(1.06) translate(0%,    0%);    }
    40%  { transform: scale(1.10) translate(-2%,  -1.5%); }
    70%  { transform: scale(1.08) translate(1.5%, -1%);   }
    100% { transform: scale(1.06) translate(0%,    0%);   }
  }
  @keyframes shotLoop2 {
    0%   { transform: scale(1.08) translate(0%,   0%);   }
    35%  { transform: scale(1.12) translate(2%,  -2%);   }
    70%  { transform: scale(1.09) translate(-1%, -1%);   }
    100% { transform: scale(1.08) translate(0%,   0%);   }
  }
  @keyframes shotFadeIn {
    from { opacity: 0; transform: translateY(10px); }
    to   { opacity: 1; transform: translateY(0); }
  }
  @keyframes skipMsgIn {
    from { opacity: 0; transform: translateY(6px); }
    to   { opacity: 1; transform: translateY(0); }
  }
`

function ShotScreen({
  shotNumber,
  totalShots,
  instruction,
  subInstruction,
  duration,
  skipLabel,
  img,
  onReady,
  onSkip,
  onBack,
}: {
  shotNumber: number
  totalShots: number
  instruction: string
  subInstruction: string
  duration?: string    // optional "6 sec" — shown beneath instructions
  skipLabel?: string   // override "Skip this shot" for context-specific language
  img: string
  onReady: () => void
  onSkip: () => void
  onBack?: () => void
}) {
  const [active, setActive] = useState(false)
  const [skipped, setSkipped] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const handleSkip = () => {
    setSkipped(true)
    setTimeout(onSkip, 1600)
  }

  // Alternate animation per shot so they feel distinct
  const animName = shotNumber % 2 === 1 ? 'shotLoop1' : 'shotLoop2'

  return (
    <ScreenWrap active={active}>
      <style>{SHOT_STYLE}</style>

      {/* Full-screen container — image fills everything, panel pinned to bottom */}
      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', overflow: 'hidden' }}>

        {/* ── Image fills entire screen ── */}
        <img
          src={img}
          alt=""
          style={{
            position: 'absolute',
            inset: 0,
            width: '100%',
            height: '100%',
            objectFit: 'cover',
            opacity: skipped ? 0.25 : 0.78,
            animation: `${animName} 7s ease-in-out infinite`,
            transformOrigin: 'center center',
            transition: 'opacity 0.4s ease',
          }}
        />

        {/* Gradient: dark at top for badges, heavy at bottom for panel legibility */}
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,11,0.45) 0%, transparent 18%, rgba(10,10,11,0.6) 55%, rgba(10,10,11,0.96) 100%)' }} />

        {/* Back — top-left (only on first shot or when explicitly provided) */}
        {onBack && !skipped && (
          <button onClick={onBack} style={{ position: 'absolute', top: 50, left: 18, zIndex: 3, background: 'rgba(10,10,11,0.4)', backdropFilter: 'blur(6px)', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.45)', padding: '5px 12px', borderRadius: 50 }}>← Back</button>
        )}

        {/* Shot counter — top-left (shifted right when Back is present) */}
        <div style={{ position: 'absolute', top: 52, left: onBack ? 100 : 22, zIndex: 2 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.14em', color: 'rgba(245,240,232,0.55)', textTransform: 'uppercase', margin: 0, background: 'rgba(10,10,11,0.4)', backdropFilter: 'blur(6px)', padding: '5px 10px', borderRadius: 50 }}>
            {shotNumber} of {totalShots}
          </p>
        </div>

        {/* Loop indicator — top-right */}
        {!skipped && (
          <div style={{ position: 'absolute', top: 52, right: 22, zIndex: 2, display: 'flex', alignItems: 'center', gap: 5, background: 'rgba(10,10,11,0.4)', backdropFilter: 'blur(6px)', padding: '5px 10px', borderRadius: 50 }}>
            <div style={{ width: 5, height: 5, borderRadius: '50%', background: '#d4a853' }} />
            <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.6)', letterSpacing: '0.07em' }}>Example</span>
          </div>
        )}

        {/* ── Panel pinned to bottom — always fully visible ── */}
        <div style={{
          position: 'absolute',
          bottom: 0, left: 0, right: 0,
          padding: '24px 24px 44px',
          boxSizing: 'border-box',
          zIndex: 2,
          animation: 'shotFadeIn 0.45s ease both',
        }}>

          {skipped ? (
            <div style={{ animation: 'skipMsgIn 0.35s ease both' }}>
              <p style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontWeight: 300,
                fontStyle: 'italic',
                fontSize: 22,
                color: 'rgba(245,240,232,0.65)',
                margin: 0,
                lineHeight: 1.4,
              }}>
                No problem. I'll work with what we have.
              </p>
            </div>
          ) : (
            <>
              <h2 style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontWeight: 300,
                fontSize: 30,
                color: '#f5f0e8',
                margin: '0 0 8px',
                lineHeight: 1.2,
              }}>
                {instruction}
              </h2>

              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 15,
                color: 'rgba(245,240,232,0.42)',
                margin: duration ? '0 0 8px' : '0 0 22px',
                lineHeight: 1.5,
              }}>
                {subInstruction}
              </p>

              {duration && (
                <p style={{
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 12,
                  color: 'rgba(245,240,232,0.22)',
                  margin: '0 0 22px',
                  letterSpacing: '0.06em',
                }}>
                  {duration}
                </p>
              )}

              <button
                onClick={onReady}
                style={{
                  width: '100%',
                  padding: '17px 0',
                  borderRadius: 50,
                  background: '#f5f0e8',
                  color: '#0a0a0b',
                  fontFamily: "'DM Sans', sans-serif",
                  fontWeight: 600,
                  fontSize: 15,
                  border: 'none',
                  cursor: 'pointer',
                  display: 'block',
                }}
              >
                Ready
              </button>

              <button
                onClick={handleSkip}
                style={{
                  marginTop: 10,
                  width: '100%',
                  padding: '13px 0',
                  borderRadius: 50,
                  background: 'transparent',
                  color: 'rgba(245,240,232,0.28)',
                  fontFamily: "'DM Sans', sans-serif",
                  fontSize: 14,
                  border: 'none',
                  cursor: 'pointer',
                  display: 'block',
                }}
              >
                {skipLabel ?? 'Skip this shot'}
              </button>
            </>
          )}
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// REUSABLE: Capture screen (countdown + record)
// ──────────────────────────────────────────────
// Live scene fills the entire frame.
// Countdown is large and centered, then disappears.
// During recording the UI shrinks to a corner dot + a thin
// arc border so the user can focus on their subject.

function CaptureScreen({
  onDone,
  onCancel,
  hint,
  img,
}: {
  onDone: () => void
  onCancel?: () => void  // exit capture — returns to shot guidance
  hint?: string          // very short reminder, e.g. "Follow behind"
  img?: string           // scene image to show as simulated camera feed
}) {
  const [phase, setPhase] = useState<'3' | '2' | '1' | 'go' | 'recording' | 'done'>('3')
  const [recProgress, setRecProgress] = useState(0)
  const [active, setActive] = useState(false)

  // Countdown: 3→2→1→GO each 1 s, then recording
  useEffect(() => {
    setActive(true)
    const steps: Array<typeof phase> = ['2', '1', 'go', 'recording']
    let i = 0
    const next = () => {
      if (i < steps.length) {
        const t = setTimeout(() => { setPhase(steps[i]); i++; next() }, 1000)
        return t
      }
    }
    const t = next()
    return () => { if (t) clearTimeout(t) }
  }, [])

  // Recording: ~4 s then auto-stop
  useEffect(() => {
    if (phase !== 'recording') return
    const duration = 4200
    const tick = 60
    let elapsed = 0
    const interval = setInterval(() => {
      elapsed += tick
      const p = Math.min((elapsed / duration) * 100, 100)
      setRecProgress(p)
      if (p >= 100) {
        clearInterval(interval)
        setPhase('done')
        setTimeout(onDone, 500)
      }
    }, tick)
    return () => clearInterval(interval)
  }, [phase, onDone])

  const isCountdown = phase === '3' || phase === '2' || phase === '1'
  const isGo        = phase === 'go'
  const isRecording = phase === 'recording'

  // Arc circumference for the thin border progress ring (r = 194 for a 390px-wide frame)
  // We'll use an SVG overlay the full width of the frame instead
  const edgeR = 192
  const edgeC = 2 * Math.PI * edgeR

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes recDot {
          0%, 100% { opacity: 1; }
          50%       { opacity: 0.25; }
        }
        @keyframes countIn {
          from { opacity: 0; transform: scale(1.3); }
          to   { opacity: 1; transform: scale(1); }
        }
        @keyframes goIn {
          from { opacity: 0; transform: scale(0.8) translateY(6px); }
          60%  { opacity: 1; transform: scale(1.05) translateY(-2px); }
          to   { opacity: 1; transform: scale(1)   translateY(0); }
        }
        @keyframes hintFade {
          0%   { opacity: 0; }
          15%  { opacity: 1; }
          75%  { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>

      <div style={{ flex: 1, position: 'relative', background: '#000', overflow: 'hidden' }}>

        {/* ── Simulated live camera feed ── */}
        <img
          src={img ?? IMG_TIMES_SQUARE_CROWD}
          alt=""
          style={{
            position: 'absolute', inset: 0,
            width: '100%', height: '100%',
            objectFit: 'cover',
            opacity: isRecording ? 0.78 : 0.55,
            transition: 'opacity 0.5s ease',
          }}
        />

        {/* Gentle vignette always present */}
        <div style={{ position: 'absolute', inset: 0, background: 'radial-gradient(ellipse at 50% 42%, transparent 35%, rgba(0,0,0,0.5) 100%)' }} />

        {/* During countdown: a soft central darkening so the number is legible */}
        {(isCountdown || isGo) && (
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(0,0,0,0.28)' }} />
        )}

        {/* ── Recording progress arc — thin border around the whole frame ── */}
        {isRecording && (
          <svg
            width="390" height="844"
            viewBox="0 0 390 844"
            style={{ position: 'absolute', inset: 0, pointerEvents: 'none' }}
          >
            {/* dim track */}
            <rect x="1" y="1" width="388" height="842" rx="0" ry="0"
              fill="none" stroke="rgba(245,240,232,0.08)" strokeWidth="2"
            />
            {/* animated fill — traces the perimeter */}
            <rect x="1" y="1" width="388" height="842" rx="0" ry="0"
              fill="none"
              stroke="rgba(245,240,232,0.55)"
              strokeWidth="2"
              strokeDasharray={`${(2 * (388 + 842))}`}
              strokeDashoffset={`${(2 * (388 + 842)) * (1 - recProgress / 100)}`}
              strokeLinecap="square"
              style={{ transition: 'stroke-dashoffset 0.06s linear' }}
            />
          </svg>
        )}

        {/* ── Countdown numbers ── */}
        {isCountdown && (
          <div
            key={phase}
            style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              animation: 'countIn 0.25s cubic-bezier(0.22,1,0.36,1) both',
            }}
          >
            <p style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontWeight: 300,
              fontSize: 110,
              color: '#f5f0e8',
              margin: 0, lineHeight: 1,
              textShadow: '0 2px 32px rgba(0,0,0,0.6)',
            }}>
              {phase}
            </p>
          </div>
        )}

        {/* ── GO ── */}
        {isGo && (
          <div
            style={{
              position: 'absolute', inset: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              animation: 'goIn 0.35s cubic-bezier(0.22,1,0.36,1) both',
            }}
          >
            <p style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontWeight: 300,
              fontSize: 72,
              color: '#d4a853',
              margin: 0, lineHeight: 1,
              letterSpacing: '0.06em',
              textShadow: '0 2px 32px rgba(0,0,0,0.5)',
            }}>
              GO
            </p>
          </div>
        )}

        {/* ── X dismiss — upper-left, visible pre-recording and during recording ── */}
        {onCancel && phase !== 'done' && (
          <button
            onClick={onCancel}
            style={{
              position: 'absolute', top: 50, left: 18, zIndex: 10,
              background: 'rgba(10,10,11,0.45)', backdropFilter: 'blur(6px)',
              border: 'none', cursor: 'pointer',
              width: 34, height: 34, borderRadius: '50%',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              color: 'rgba(245,240,232,0.5)',
              fontFamily: "'DM Sans', sans-serif", fontSize: 16, fontWeight: 300,
            }}
          >
            ✕
          </button>
        )}

        {/* ── Recording: corner dot only ── */}
        {isRecording && (
          <div style={{ position: 'absolute', top: 52, right: 20, display: 'flex', alignItems: 'center', gap: 6 }}>
            <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#e84040', animation: 'recDot 1.1s ease-in-out infinite' }} />
          </div>
        )}

        {/* ── Subtle hint — bottom, appears mid-recording, fades out ── */}
        {isRecording && hint && (
          <p style={{
            position: 'absolute',
            bottom: 52,
            left: 0, right: 0,
            textAlign: 'center',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 14,
            color: 'rgba(245,240,232,0.45)',
            margin: 0,
            animation: 'hintFade 3.5s ease forwards',
            pointerEvents: 'none',
          }}>
            {hint}
          </p>
        )}
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN 8 — Validation (success or retry)
// ──────────────────────────────────────────────
function Screen8Validation({
  result,
  reason,
  nextLabel,
  autoAdvance,
  onNext,
  onRetry,
  onUseAnyway,
}: {
  result: 'success' | 'retry'
  reason?: string
  nextLabel?: string
  autoAdvance?: boolean   // success only: auto-proceed after brief pause
  onNext: () => void
  onRetry?: () => void
  onUseAnyway?: () => void
}) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  useEffect(() => {
    if (result === 'success' && autoAdvance) {
      const t = setTimeout(onNext, 1800)
      return () => clearTimeout(t)
    }
  }, [result, autoAdvance, onNext])

  const isSuccess = result === 'success'

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes validIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0a0a0b',
        padding: '0 32px',
        gap: 0,
      }}>

        {isSuccess ? (
          /* ── SUCCESS ── */
          <>
            <div style={{
              width: 68,
              height: 68,
              borderRadius: '50%',
              background: 'rgba(212,168,83,0.1)',
              border: '1.5px solid rgba(212,168,83,0.35)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              transform: show ? 'scale(1)' : 'scale(0.55)',
              opacity: show ? 1 : 0,
              transition: 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1), opacity 0.3s',
              marginBottom: 20,
            }}>
              <span style={{ fontSize: 26, color: '#d4a853' }}>✓</span>
            </div>

            <p style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontWeight: 300,
              fontSize: 30,
              color: '#f5f0e8',
              margin: '0 0 32px',
              opacity: show ? 1 : 0,
              transition: 'opacity 0.4s 0.1s',
              textAlign: 'center',
            }}>
              Got it.
            </p>

            {!autoAdvance && (
              <button
                onClick={onNext}
                style={{
                  padding: '16px 52px',
                  borderRadius: 50,
                  background: '#f5f0e8',
                  color: '#0a0a0b',
                  fontFamily: "'DM Sans', sans-serif",
                  fontWeight: 600,
                  fontSize: 15,
                  border: 'none',
                  cursor: 'pointer',
                  opacity: show ? 1 : 0,
                  transition: 'opacity 0.35s 0.18s',
                }}
              >
                {nextLabel ?? 'Next shot'}
              </button>
            )}
          </>
        ) : (
          /* ── RETRY ── */
          <>
            <p style={{
              fontFamily: "'Fraunces', Georgia, serif",
              fontWeight: 300,
              fontSize: 28,
              color: '#f5f0e8',
              margin: '0 0 12px',
              textAlign: 'center',
              opacity: show ? 1 : 0,
              transition: 'opacity 0.35s',
              lineHeight: 1.2,
            }}>
              Almost got it.
            </p>

            {reason && (
              <p style={{
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 15,
                color: 'rgba(245,240,232,0.45)',
                margin: '0 0 36px',
                textAlign: 'center',
                lineHeight: 1.55,
                opacity: show ? 1 : 0,
                transition: 'opacity 0.35s 0.08s',
              }}>
                {reason}
              </p>
            )}

            <button
              onClick={onRetry}
              style={{
                width: '100%',
                padding: '17px 0',
                borderRadius: 50,
                background: '#f5f0e8',
                color: '#0a0a0b',
                fontFamily: "'DM Sans', sans-serif",
                fontWeight: 600,
                fontSize: 15,
                border: 'none',
                cursor: 'pointer',
                marginBottom: 12,
                opacity: show ? 1 : 0,
                transition: 'opacity 0.35s 0.14s',
              }}
            >
              Try again
            </button>

            <button
              onClick={onUseAnyway ?? onNext}
              style={{
                width: '100%',
                padding: '14px 0',
                borderRadius: 50,
                background: 'transparent',
                color: 'rgba(245,240,232,0.3)',
                fontFamily: "'DM Sans', sans-serif",
                fontSize: 14,
                border: 'none',
                cursor: 'pointer',
                opacity: show ? 1 : 0,
                transition: 'opacity 0.35s 0.2s',
              }}
            >
              Use anyway
            </button>
          </>
        )}
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN: Final capture complete — create or add media
// ──────────────────────────────────────────────
function ScreenFinalCapture({
  onCreateNow, track, userPicked, onChangeMusic,
}: {
  onCreateNow: () => void
  track: MusicTrack
  userPicked: boolean
  onChangeMusic: () => void
}) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes finalIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: '#0a0a0b', padding: '0 32px',
      }}>
        {/* Checkmark */}
        <div style={{
          width: 68, height: 68, borderRadius: '50%',
          background: 'rgba(212,168,83,0.1)',
          border: '1.5px solid rgba(212,168,83,0.35)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transform: show ? 'scale(1)' : 'scale(0.55)',
          opacity: show ? 1 : 0,
          transition: 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1), opacity 0.3s',
          marginBottom: 20,
        }}>
          <span style={{ fontSize: 26, color: '#d4a853' }}>✓</span>
        </div>

        <p style={{
          fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300,
          fontSize: 30, color: '#f5f0e8', margin: '0 0 10px',
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.08s',
          textAlign: 'center',
        }}>
          Got it.
        </p>

        <p style={{
          fontFamily: "'DM Sans', sans-serif", fontSize: 15,
          color: 'rgba(245,240,232,0.38)', margin: '0 0 36px',
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.14s',
          textAlign: 'center', lineHeight: 1.5,
        }}>
          That's everything I need.
        </p>

        <div style={{ width: '100%', marginBottom: 28, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.18s' }}>
          <MusicPick track={track} userPicked={userPicked} onChangeMusic={onChangeMusic} />
        </div>

        {/* Actions */}
        <div style={{ width: '100%', opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.2s' }}>
          <button
            onClick={onCreateNow}
            style={{
              width: '100%', padding: '17px 0', borderRadius: 50,
              background: '#f5f0e8', color: '#0a0a0b',
              fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15,
              border: 'none', cursor: 'pointer',
            }}
          >
            Create my Story
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN: Media picker — simulated camera roll
// ──────────────────────────────────────────────
function ScreenMediaPicker({
  initialSelected,
  onBack,
  onDone,
}: {
  initialSelected: string[]
  onBack: () => void
  onDone: (selected: string[]) => void
}) {
  const [selected, setSelected] = useState<string[]>(initialSelected)
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const toggle = (id: string) => {
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])
  }

  const handleDone = () => {
    if (selected.length === 0) { onBack(); return }
    onDone(selected)
  }

  const cellSize = (390 - 3) / 3  // 3-column grid, 1px gaps

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes pickerIn {
          from { opacity: 0; }
          to   { opacity: 1; }
        }
      `}</style>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0b', overflow: 'hidden' }}>

        {/* Top bar */}
        <div style={{
          display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          padding: '52px 20px 14px',
          borderBottom: '1px solid rgba(245,240,232,0.06)',
          flexShrink: 0,
        }}>
          <button
            onClick={onBack}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontFamily: "'DM Sans', sans-serif", fontSize: 14,
              color: 'rgba(245,240,232,0.45)', padding: '4px 0',
            }}
          >
            ← Back
          </button>

          <span style={{
            fontFamily: "'DM Sans', sans-serif", fontSize: 13,
            color: 'rgba(245,240,232,0.55)', fontWeight: 500,
          }}>
            Camera Roll
          </span>

          <button
            onClick={handleDone}
            style={{
              background: 'none', border: 'none', cursor: 'pointer',
              fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 600,
              color: selected.length > 0 ? '#f5f0e8' : 'rgba(245,240,232,0.22)',
              padding: '4px 0',
              transition: 'color 0.2s',
            }}
          >
            {selected.length > 0 ? `Add ${selected.length}` : 'Done'}
          </button>
        </div>

        {/* Grid */}
        <div style={{
          flex: 1, overflowY: 'auto',
          display: 'grid',
          gridTemplateColumns: 'repeat(3, 1fr)',
          gap: 1.5,
          alignContent: 'start',
        }}>
          {CAMERA_ROLL.map((item) => {
            const isSelected = selected.includes(item.id)
            return (
              <div
                key={item.id}
                onClick={() => toggle(item.id)}
                style={{
                  position: 'relative',
                  aspectRatio: '3/4',
                  background: '#1a1a1c',
                  cursor: 'pointer',
                  overflow: 'hidden',
                }}
              >
                <img
                  src={item.src}
                  alt=""
                  style={{
                    width: '100%', height: '100%', objectFit: 'cover',
                    opacity: isSelected ? 0.6 : 0.85,
                    transition: 'opacity 0.15s',
                  }}
                />

                {/* Video indicator */}
                {item.video && !isSelected && (
                  <div style={{
                    position: 'absolute', bottom: 6, left: 7,
                    display: 'flex', alignItems: 'center', gap: 4,
                  }}>
                    <div style={{
                      width: 0, height: 0,
                      borderTop: '4px solid transparent',
                      borderBottom: '4px solid transparent',
                      borderLeft: '6px solid rgba(245,240,232,0.8)',
                    }} />
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: 'rgba(245,240,232,0.7)' }}>0:12</span>
                  </div>
                )}

                {/* Selection badge */}
                {isSelected && (
                  <div style={{
                    position: 'absolute', top: 7, right: 7,
                    width: 22, height: 22, borderRadius: '50%',
                    background: '#d4a853',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                  }}>
                    <span style={{ fontSize: 11, color: '#0a0a0b', fontWeight: 700 }}>✓</span>
                  </div>
                )}

                {/* Unselected ring placeholder — shows position */}
                {!isSelected && (
                  <div style={{
                    position: 'absolute', top: 7, right: 7,
                    width: 20, height: 20, borderRadius: '50%',
                    border: '1.5px solid rgba(245,240,232,0.3)',
                  }} />
                )}
              </div>
            )
          })}
        </div>

        {/* Bottom selection hint */}
        {selected.length > 0 && (
          <div style={{
            padding: '12px 24px 32px', background: '#0a0a0b',
            borderTop: '1px solid rgba(245,240,232,0.06)',
            display: 'flex', justifyContent: 'center',
            flexShrink: 0,
          }}>
            <p style={{
              fontFamily: "'DM Sans', sans-serif", fontSize: 13,
              color: 'rgba(245,240,232,0.32)', margin: 0,
            }}>
              {selected.length} {selected.length === 1 ? 'item' : 'items'} selected
            </p>
          </div>
        )}
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// PRE-SHOOT MEDIA: Analysis — "Let me see what you already have."
// ──────────────────────────────────────────────
function ScreenPreMediaAnalysis({ onDone }: { onDone: () => void }) {
  const [active, setActive] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(onDone, 2800)
    return () => clearTimeout(t)
  }, [onDone])

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes analyzePulse {
          0%, 100% { opacity: 0.15; transform: scale(0.85); }
          50%       { opacity: 0.65; transform: scale(1.15); }
        }
        @keyframes analyzeFadeIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{
        flex: 1, position: 'relative', background: '#0a0a0b',
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        {/* Faint image of selected clip behind */}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          <img src={IMG_TIMES_SQUARE_WIDE} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.18 }} />
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.7)' }} />
        </div>

        <div style={{
          position: 'relative', zIndex: 2,
          display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 24,
          animation: 'analyzeFadeIn 0.5s ease both',
        }}>
          <div style={{ display: 'flex', gap: 9 }}>
            {[0, 1, 2].map(i => (
              <div key={i} style={{
                width: 6, height: 6, borderRadius: '50%', background: '#f5f0e8',
                animation: `analyzePulse 2s ease-in-out ${i * 0.32}s infinite`,
              }} />
            ))}
          </div>
          <p style={{
            fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300,
            fontStyle: 'italic', fontSize: 22,
            color: 'rgba(245,240,232,0.65)', margin: 0, textAlign: 'center',
          }}>
            Let me see what you already have.
          </p>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// PRE-SHOOT MEDIA OUTCOME A — existing clip replaces a planned shot
// "Nice — you already have the reveal."
// ──────────────────────────────────────────────
function ScreenPreMediaResultA({ onShoot }: { onShoot: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes resultAIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: '#0a0a0b', padding: '56px 24px 36px', overflowY: 'auto',
      }}>
        <p style={{
          fontFamily: "'DM Sans', sans-serif", fontSize: 12,
          letterSpacing: '0.12em', color: 'rgba(245,240,232,0.3)',
          textTransform: 'uppercase', margin: '0 0 22px',
          opacity: show ? 1 : 0, transition: 'opacity 0.4s',
        }}>Story</p>

        <h2 style={{
          fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300,
          fontSize: 26, color: '#f5f0e8', margin: '0 0 6px', lineHeight: 1.25,
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.06s',
        }}>
          Nice — you already have the reveal.
        </h2>

        <p style={{
          fontFamily: "'DM Sans', sans-serif", fontSize: 14,
          color: 'rgba(245,240,232,0.38)', margin: '0 0 26px', lineHeight: 1.5,
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.1s',
        }}>
          Just one shot left.
        </p>

        {/* Updated storyboard */}
        <div style={{
          display: 'flex', gap: 10, marginBottom: 20, flexShrink: 0,
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.14s',
        }}>
          {/* Shot 1 — still needs capture */}
          <div style={{
            flex: 1, borderRadius: 14, overflow: 'hidden',
            position: 'relative', aspectRatio: '9/14', background: '#1a1a1c',
            border: '1.5px solid rgba(245,240,232,0.2)',
          }}>
            <img src={IMG_TIMES_SQUARE_CROWD} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.72 }} />
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.82) 0%, transparent 50%)' }} />
            <div style={{ position: 'absolute', bottom: 10, left: 10 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: '0 0 2px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Shot 1</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.6)', margin: 0 }}>Let's capture this</p>
            </div>
            <div style={{ position: 'absolute', top: 8, left: 10, fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.4)' }}>1</div>
          </div>

          {/* Shot 2 — covered by existing clip */}
          <div style={{
            flex: 1, borderRadius: 14, overflow: 'hidden',
            position: 'relative', aspectRatio: '9/14', background: '#1a1a1c',
            border: '1.5px solid rgba(212,168,83,0.4)',
          }}>
            <img src={IMG_TIMES_SQUARE_WIDE} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.45 }} />
            <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.45)' }} />
            <div style={{ position: 'absolute', bottom: 10, left: 10 }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: '0 0 2px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>Existing clip</p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.45)', margin: 0 }}>Reveal covered</p>
            </div>
            {/* Gold checkmark badge */}
            <div style={{
              position: 'absolute', top: 8, right: 10,
              width: 20, height: 20, borderRadius: '50%',
              background: '#d4a853',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}>
              <span style={{ fontSize: 10, color: '#0a0a0b', fontWeight: 700 }}>✓</span>
            </div>
          </div>
        </div>

        {/* Updated metadata pill */}
        <div style={{
          display: 'inline-flex', alignSelf: 'flex-start',
          padding: '7px 14px', borderRadius: 50,
          border: '1px solid rgba(245,240,232,0.12)', marginBottom: 28,
          opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.18s',
        }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.45)' }}>
            1 shot left · ~10 sec to capture
          </span>
        </div>

        <div style={{ flex: 1 }} />

        <button
          onClick={onShoot}
          style={{
            width: '100%', padding: '17px 0', borderRadius: 50,
            background: '#f5f0e8', color: '#0a0a0b',
            fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15,
            border: 'none', cursor: 'pointer',
            opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.22s',
          }}
        >
          Let's shoot it
        </button>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// PRE-SHOOT MEDIA OUTCOME B — media helps but doesn't replace a shot
// "These will work nicely in the Story."
// ──────────────────────────────────────────────
function ScreenPreMediaResultB({ onShoot }: { onShoot: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        background: '#0a0a0b', padding: '56px 24px 36px', overflowY: 'auto',
      }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.3)', textTransform: 'uppercase', margin: '0 0 22px', opacity: show ? 1 : 0, transition: 'opacity 0.4s' }}>Story</p>

        <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 26, color: '#f5f0e8', margin: '0 0 10px', lineHeight: 1.25, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.06s' }}>
          These will work nicely in the Story.
        </h2>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.38)', margin: '0 0 26px', lineHeight: 1.5, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.1s' }}>
          I still need both shots from you.
        </p>

        {/* Original storyboard — unchanged */}
        <div style={{ display: 'flex', gap: 10, marginBottom: 20, flexShrink: 0, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.14s' }}>
          {[
            { img: IMG_TIMES_SQUARE_CROWD, label: 'Shot 1', desc: 'Walk into the crowd' },
            { img: IMG_TIMES_SQUARE_WIDE, label: 'Shot 2', desc: 'Look up at the lights' },
          ].map((shot, i) => (
            <div key={i} style={{ flex: 1, borderRadius: 14, overflow: 'hidden', position: 'relative', aspectRatio: '9/14', background: '#1a1a1c', border: '1.5px solid rgba(245,240,232,0.1)' }}>
              <img src={shot.img} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(0,0,0,0.75) 0%, transparent 50%)' }} />
              <div style={{ position: 'absolute', bottom: 10, left: 10 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: '0 0 2px', textTransform: 'uppercase', letterSpacing: '0.08em' }}>{shot.label}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.6)', margin: 0 }}>{shot.desc}</p>
              </div>
            </div>
          ))}
        </div>

        <div style={{ display: 'inline-flex', alignSelf: 'flex-start', padding: '7px 14px', borderRadius: 50, border: '1px solid rgba(245,240,232,0.12)', marginBottom: 28, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.18s' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.45)' }}>8 sec · 2 shots</span>
        </div>

        <div style={{ flex: 1 }} />

        <button onClick={onShoot} style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.22s' }}>
          Let's shoot
        </button>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// PRE-SHOOT MEDIA OUTCOME C — existing media covers everything
// "You already have what I need."
// ──────────────────────────────────────────────
function ScreenPreMediaResultC({ onCreate }: { onCreate: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{
        flex: 1, display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
        background: '#0a0a0b', padding: '0 32px',
      }}>
        <div style={{
          width: 68, height: 68, borderRadius: '50%',
          background: 'rgba(212,168,83,0.1)', border: '1.5px solid rgba(212,168,83,0.35)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          transform: show ? 'scale(1)' : 'scale(0.55)',
          opacity: show ? 1 : 0,
          transition: 'transform 0.4s cubic-bezier(0.34,1.56,0.64,1), opacity 0.3s',
          marginBottom: 20,
        }}>
          <span style={{ fontSize: 26, color: '#d4a853' }}>✓</span>
        </div>

        <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 28, color: '#f5f0e8', margin: '0 0 12px', textAlign: 'center', opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.08s' }}>
          You already have what I need.
        </p>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.38)', margin: '0 0 48px', textAlign: 'center', lineHeight: 1.5, opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.14s' }}>
          No shooting needed.
        </p>

        <button
          onClick={onCreate}
          style={{
            width: '100%', padding: '17px 0', borderRadius: 50,
            background: '#f5f0e8', color: '#0a0a0b',
            fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15,
            border: 'none', cursor: 'pointer',
            opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.2s',
          }}
        >
          Create my Story
        </button>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN 10 — Creating
// ──────────────────────────────────────────────
function Screen10Creating({ onNext, trackName, mode = 'new' }: { onNext: () => void; trackName?: string; mode?: 'new' | 'reedit' | 'version' }) {
  const [active, setActive] = useState(false)
  const [progress, setProgress] = useState(0)
  useEffect(() => {
    setActive(true)
    let p = 0
    const interval = setInterval(() => {
      p += 1.2
      setProgress(Math.min(p, 100))
      if (p >= 100) {
        clearInterval(interval)
        setTimeout(onNext, 500)
      }
    }, 30)
    return () => clearInterval(interval)
  }, [onNext])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0a0a0b', gap: 28, padding: '0 40px' }}>
        <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 24, color: 'rgba(245,240,232,0.7)', margin: 0, textAlign: 'center' }}>
          {mode === 'reedit' && trackName ? `Re-editing to fit ${trackName}…` : mode === 'version' ? 'Creating a new version…' : 'Creating your Story...'}
        </p>
        {trackName && (() => {
          const lines = ['Reading your moments', `Listening to ${trackName}`, 'Shaping the story around the music', 'Timing every cut to the music']
          const i = Math.min(lines.length - 1, Math.floor(progress / (100 / lines.length)))
          return (
            <p key={i} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.35)', margin: '-12px 0 0', textAlign: 'center' }}>
              {lines[i]}…
            </p>
          )
        })()}
        <div style={{ width: '100%', height: 1.5, borderRadius: 2, background: 'rgba(255,255,255,0.06)', overflow: 'hidden' }}>
          <div style={{ height: '100%', background: 'linear-gradient(to right, rgba(245,240,232,0.3), rgba(245,240,232,0.8))', width: `${progress}%`, transition: 'width 0.03s linear', borderRadius: 2 }} />
        </div>
      </div>
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// SCREEN 11 — Result
// ──────────────────────────────────────────────
function Screen11Result({ onRestart, onHome, trackName, onChangeMusic, image = IMG_NEON_STREET, title = 'Your Story', length = '8 sec' }: { onRestart: () => void; onHome: () => void; trackName?: string; onChangeMusic?: () => void; image?: string; title?: string; length?: string }) {
  const [playing, setPlaying] = useState(false)
  const [feedbackOpen, setFeedbackOpen] = useState(false)
  const [feedbackText, setFeedbackText] = useState('')
  const [feedbackSent, setFeedbackSent] = useState(false)
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const submitFeedback = () => {
    if (!feedbackText.trim()) return
    setFeedbackSent(true)
    setTimeout(() => {
      setFeedbackOpen(false)
      setFeedbackSent(false)
      setFeedbackText('')
    }, 1800)
  }

  return (
    <ScreenWrap active={active}>
      <style>{`
        ${EQ_STYLE}
        @keyframes resultFadeUp {
          from { opacity: 0; transform: translateY(12px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes feedbackSlide {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>

        {/* ── Header ── */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, zIndex: 4, padding: '52px 24px 0', display: 'flex', alignItems: 'baseline', justifyContent: 'space-between' }}>
          <button onClick={onHome} aria-label="Home" style={{ position: 'absolute', top: 20, left: 22, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.55)', padding: 0 }}>← Home</button>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 26, color: '#f5f0e8', margin: 0, animation: 'resultFadeUp 0.5s ease both' }}>
            {title}
          </h2>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.3)', animation: 'resultFadeUp 0.5s ease 0.05s both' }}>
            {length}
          </span>
        </div>
        {trackName && (
          <p style={{ position: 'absolute', top: 90, left: 24, zIndex: 4, margin: 0, fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.65)', display: 'flex', alignItems: 'center', gap: 7, animation: 'resultFadeUp 0.5s ease 0.08s both' }}>
            <EqBars playing={playing} size={11} color="rgba(245,240,232,0.7)" /> ♫ {trackName}
          </p>
        )}

        {/* ── Large vertical video — dominates the screen ── */}
        <div
          onClick={() => setPlaying(p => !p)}
          style={{
            position: 'absolute',
            top: 0, left: 0, right: 0,
            bottom: 186,           // space for the action panel below
            cursor: 'pointer',
            background: '#111',
            overflow: 'hidden',
          }}
        >
          <img
            src={image}
            alt="Your story"
            style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.9 }}
          />
          {/* Scrim: heavier at top (behind header) and very subtle at bottom */}
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,11,0.65) 0%, transparent 22%, transparent 70%, rgba(10,10,11,0.4) 100%)' }} />

          {/* Play/pause button — center, only when paused */}
          {!playing && (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
              <div style={{
                width: 64, height: 64, borderRadius: '50%',
                background: 'rgba(10,10,11,0.45)', backdropFilter: 'blur(10px)',
                border: '1px solid rgba(245,240,232,0.18)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
              }}>
                <div style={{ width: 0, height: 0, borderTop: '11px solid transparent', borderBottom: '11px solid transparent', borderLeft: '18px solid #f5f0e8', marginLeft: 5 }} />
              </div>
            </div>
          )}

          {/* Minimal scrubber — bottom of video area */}
          <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '0 20px 14px' }}>
            <div style={{ height: 2, borderRadius: 2, background: 'rgba(255,255,255,0.18)', overflow: 'hidden' }}>
              <div style={{ height: '100%', borderRadius: 2, background: 'rgba(245,240,232,0.75)', width: playing ? '62%' : '0%', transition: 'width 0.4s ease' }} />
            </div>
          </div>
        </div>

        {/* ── Action panel — pinned to bottom ── */}
        <div style={{
          position: 'absolute',
          bottom: 0, left: 0, right: 0,
          height: 186,
          background: '#0a0a0b',
          padding: '16px 24px 40px',
          boxSizing: 'border-box',
          display: 'flex',
          flexDirection: 'column',
          gap: 0,
          animation: 'resultFadeUp 0.5s ease 0.1s both',
        }}>

          {/* Primary: Save */}
          <button
            style={{
              width: '100%', padding: '16px 0', borderRadius: 50,
              background: '#f5f0e8', color: '#0a0a0b',
              fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15,
              border: 'none', cursor: 'pointer', marginBottom: 10,
            }}
          >
            Save
          </button>

          {/* Secondary: Create a new version */}
          <button
            onClick={onRestart}
            style={{
              width: '100%', padding: '13px 0', borderRadius: 50,
              background: 'transparent', color: 'rgba(245,240,232,0.38)',
              fontFamily: "'DM Sans', sans-serif", fontSize: 14,
              border: '1.5px solid rgba(245,240,232,0.1)', cursor: 'pointer',
              marginBottom: 14,
            }}
          >
            Create a new version
          </button>

          {/* Tertiary feedback prompt — appears only when feedback isn't open */}
          {!feedbackOpen && !feedbackSent && (
            <div style={{ display: 'flex', justifyContent: 'center', gap: 18 }}>
              {onChangeMusic && (
                <button onClick={onChangeMusic} style={{ background: 'none', border: 'none', cursor: 'pointer', padding: 0, fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(212,168,83,0.8)' }}>
                  ♫ Change music
                </button>
              )}
              <button
                onClick={() => setFeedbackOpen(true)}
                style={{
                  background: 'none', border: 'none', cursor: 'pointer', padding: 0,
                  fontFamily: "'DM Sans', sans-serif", fontSize: 13,
                  color: 'rgba(245,240,232,0.22)',
                }}
              >
                Something you'd change?
              </button>
            </div>
          )}
        </div>

        {/* ── Feedback sheet — slides up over the action panel ── */}
        {feedbackOpen && (
          <div style={{
            position: 'absolute',
            bottom: 0, left: 0, right: 0,
            background: '#141416',
            borderTop: '1px solid rgba(245,240,232,0.07)',
            padding: '20px 24px 44px',
            boxSizing: 'border-box',
            zIndex: 10,
            animation: 'feedbackSlide 0.3s ease both',
          }}>
            {feedbackSent ? (
              <p style={{
                fontFamily: "'Fraunces', Georgia, serif",
                fontWeight: 300, fontStyle: 'italic',
                fontSize: 18, color: 'rgba(245,240,232,0.55)',
                margin: 0, textAlign: 'center', padding: '10px 0',
                animation: 'feedbackSlide 0.3s ease both',
              }}>
                Got it. I'll adjust.
              </p>
            ) : (
              <>
                <textarea
                  autoFocus
                  value={feedbackText}
                  onChange={e => setFeedbackText(e.target.value)}
                  placeholder={"More of the city.\nToo much of me.\nMake it faster."}
                  style={{
                    width: '100%', borderRadius: 14,
                    border: '1.5px solid rgba(245,240,232,0.1)',
                    background: 'rgba(255,255,255,0.04)',
                    color: '#f5f0e8',
                    fontFamily: "'DM Sans', sans-serif", fontSize: 14,
                    padding: '13px 15px', resize: 'none', height: 80,
                    outline: 'none', boxSizing: 'border-box', marginBottom: 12,
                  }}
                />
                <div style={{ display: 'flex', gap: 10 }}>
                  <button
                    onClick={() => setFeedbackOpen(false)}
                    style={{
                      flex: 1, padding: '13px 0', borderRadius: 50,
                      background: 'transparent', color: 'rgba(245,240,232,0.28)',
                      fontFamily: "'DM Sans', sans-serif", fontSize: 14,
                      border: '1.5px solid rgba(245,240,232,0.08)', cursor: 'pointer',
                    }}
                  >
                    Cancel
                  </button>
                  <button
                    onClick={submitFeedback}
                    style={{
                      flex: 2, padding: '13px 0', borderRadius: 50,
                      background: feedbackText.trim() ? '#f5f0e8' : 'rgba(245,240,232,0.12)',
                      color: feedbackText.trim() ? '#0a0a0b' : 'rgba(245,240,232,0.25)',
                      fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 14,
                      border: 'none', cursor: feedbackText.trim() ? 'pointer' : 'default',
                      transition: 'background 0.2s, color 0.2s',
                    }}
                  >
                    Send
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// HOME SCREEN
// Entry point — Create now, Start a Story, Existing media
// ══════════════════════════════════════════════
function ScreenHome({
  tmbCreated,
  tmbCompleted,
  momentCount,
  onCreateNow,
  onStartStory,
  onExistingMedia,
  onTMB,
}: {
  tmbCreated: boolean
  tmbCompleted: boolean
  momentCount: number
  onCreateNow: () => void
  onStartStory: () => void
  onExistingMedia: () => void
  onTMB: () => void
}) {
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const smCard: React.CSSProperties = {
    position: 'relative', borderRadius: 16, overflow: 'hidden',
    aspectRatio: '16/9', cursor: 'pointer', background: '#1a1a1c',
    display: 'block', width: '100%', border: 'none', padding: 0,
  }

  const lgCard: React.CSSProperties = {
    position: 'relative', borderRadius: 20, overflow: 'hidden',
    aspectRatio: '16/9', cursor: 'pointer', background: '#1a1a1c',
    display: 'block', width: '100%', border: 'none', padding: 0,
  }

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes homeIn {
          from { opacity: 0; transform: translateY(14px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{ flex: 1, background: '#0a0a0b', overflowY: 'auto', padding: '56px 20px 40px', display: 'flex', flexDirection: 'column' }}>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.14em', color: 'rgba(245,240,232,0.28)', textTransform: 'uppercase', margin: '0 0 22px' }}>Story</p>

        {tmbCreated ? (
          /* ── ACTIVE STORY MODE ── */
          <>
            {/* Active Story — primary hero card (only while active) */}
            {!tmbCompleted && <div style={{ marginBottom: 32, animation: 'homeIn 0.4s ease both' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 11px' }}>Continue</p>
              <button
                onClick={onTMB}
                style={{ width: '100%', borderRadius: 20, overflow: 'hidden', cursor: 'pointer', border: '1px solid rgba(245,240,232,0.09)', background: 'none', padding: 0, textAlign: 'left', display: 'block' }}
              >
                {/* Mosaic — taller than the old mini strip */}
                <div style={{ display: 'flex', height: 110, gap: 2 }}>
                  {[IMG_ALPS_PANORAMA, IMG_MOUNTAIN_TRAIL, IMG_MOUNTAIN_LAKE].map((src, i) => (
                    <div key={i} style={{ flex: i === 0 ? 1.6 : 1, overflow: 'hidden' }}>
                      <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.88 }} />
                    </div>
                  ))}
                </div>
                {/* Card body */}
                <div style={{ background: 'rgba(255,255,255,0.03)', padding: '14px 16px 16px' }}>
                  <div style={{ marginBottom: 10 }}>
                    <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: '0 0 2px', lineHeight: 1.2 }}>Tour du Mont Blanc</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.22)', margin: 0, letterSpacing: '0.04em' }}>Day 3 of 8</p>
                  </div>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.48)', margin: 0 }}>Your Story is taking shape.</p>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.38)', whiteSpace: 'nowrap', marginLeft: 12 }}>Continue →</span>
                  </div>
                </div>
              </button>
            </div>}

            {/* Section: Create */}
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 11px', animation: 'homeIn 0.4s ease 0.07s both' }}>Create</p>

            {/* Create now — compact row button */}
            <button
              onClick={onCreateNow}
              style={{ ...smCard, marginBottom: 8, animation: 'homeIn 0.4s ease 0.08s both' }}
            >
              <img src={IMG_TIMES_SQUARE_NIGHT} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.65 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,11,0.92) 0%, rgba(10,10,11,0.2) 60%, transparent 100%)' }} />
              <div style={{ position: 'absolute', bottom: 12, left: 16 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.38)', textTransform: 'uppercase', margin: '0 0 2px' }}>Right now</p>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: 0 }}>Create now</h3>
              </div>
              <span style={{ position: 'absolute', top: 12, right: 14, fontSize: 14, color: 'rgba(245,240,232,0.35)' }}>→</span>
            </button>

            {/* Start a Story — compact */}
            <button
              onClick={onStartStory}
              style={{ ...smCard, marginBottom: 16, animation: 'homeIn 0.4s ease 0.11s both' }}
            >
              <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.65 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,11,0.92) 0%, rgba(10,10,11,0.2) 60%, transparent 100%)' }} />
              <div style={{ position: 'absolute', bottom: 12, left: 16 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.38)', textTransform: 'uppercase', margin: '0 0 2px' }}>Over time</p>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: 0 }}>Start a Story</h3>
              </div>
              <span style={{ position: 'absolute', top: 12, right: 14, fontSize: 14, color: 'rgba(245,240,232,0.35)' }}>→</span>
            </button>

            {/* Your Stories section — previous / completed */}
            <div style={{ animation: 'homeIn 0.4s ease 0.18s both' }}>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 11px' }}>Your Stories</p>
              {/* Completed persistent Story — most recently completed first */}
              {tmbCompleted && (
                <button
                  onClick={onTMB}
                  style={{ width: '100%', borderRadius: 14, overflow: 'hidden', cursor: 'pointer', border: '1px solid rgba(245,240,232,0.07)', background: 'none', padding: 0, textAlign: 'left', display: 'block', marginBottom: 8 }}
                >
                  <div style={{ display: 'flex', height: 56, gap: 1 }}>
                    {[IMG_ALPS_PANORAMA, IMG_MOUNTAIN_TRAIL, IMG_MOUNTAIN_LAKE].map((src, i) => (
                      <div key={i} style={{ flex: 1, overflow: 'hidden' }}>
                        <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }} />
                      </div>
                    ))}
                  </div>
                  <div style={{ padding: '10px 14px 12px', background: 'rgba(255,255,255,0.02)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                    <div>
                      <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 14, color: 'rgba(245,240,232,0.6)', margin: '0 0 1px' }}>Tour du Mont Blanc</p>
                      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: 'rgba(245,240,232,0.2)', margin: 0 }}>Completed · {momentCount} moments</p>
                    </div>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.2)' }}>View →</span>
                  </div>
                </button>
              )}
              {/* Placeholder past Story */}
              <button
                style={{ width: '100%', borderRadius: 14, overflow: 'hidden', cursor: 'pointer', border: '1px solid rgba(245,240,232,0.07)', background: 'none', padding: 0, textAlign: 'left', display: 'block', marginBottom: 8 }}
              >
                <div style={{ display: 'flex', height: 56, gap: 1 }}>
                  {[IMG_TIMES_SQUARE_NIGHT, IMG_TIMES_SQUARE_CROWD, IMG_TIMES_SQUARE_SIGNS].map((src, i) => (
                    <div key={i} style={{ flex: 1, overflow: 'hidden' }}>
                      <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.7 }} />
                    </div>
                  ))}
                </div>
                <div style={{ padding: '10px 14px 12px', background: 'rgba(255,255,255,0.02)', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 14, color: 'rgba(245,240,232,0.6)', margin: '0 0 1px' }}>New York, New Year's</p>
                    <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, color: 'rgba(245,240,232,0.2)', margin: 0 }}>Completed · Dec 2024</p>
                  </div>
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.2)' }}>View →</span>
                </div>
              </button>
            </div>
          </>
        ) : (
          /* ── NO ACTIVE STORY — creation-first ── */
          <>
            <h1 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 28, color: '#f5f0e8', lineHeight: 1.2, margin: '0 0 22px' }}>
              What would you<br />like to make?
            </h1>

            {/* Create now card */}
            <button onClick={onCreateNow} style={{ ...lgCard, marginBottom: 10, animation: 'homeIn 0.4s ease both' }}>
              <img src={IMG_TIMES_SQUARE_NIGHT} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.72 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,11,0.94) 0%, rgba(10,10,11,0.25) 60%, transparent 100%)' }} />
              <div style={{ position: 'absolute', bottom: 15, left: 18 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.14em', color: 'rgba(245,240,232,0.4)', textTransform: 'uppercase', margin: '0 0 3px' }}>Right now</p>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 21, color: '#f5f0e8', margin: '0 0 2px' }}>Create now</h3>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.42)', margin: 0 }}>Make something here, in this moment.</p>
              </div>
              <span style={{ position: 'absolute', top: 14, right: 16, fontSize: 15, color: 'rgba(245,240,232,0.4)' }}>→</span>
            </button>

            {/* Start a Story card */}
            <button onClick={onStartStory} style={{ ...lgCard, marginBottom: 22, animation: 'homeIn 0.4s ease 0.07s both' }}>
              <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.78 }} />
              <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,11,0.94) 0%, rgba(10,10,11,0.2) 60%, transparent 100%)' }} />
              <div style={{ position: 'absolute', bottom: 15, left: 18 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.14em', color: 'rgba(245,240,232,0.4)', textTransform: 'uppercase', margin: '0 0 3px' }}>Over time</p>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 21, color: '#f5f0e8', margin: '0 0 2px' }}>Start a Story</h3>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.42)', margin: 0 }}>Capture an experience as it unfolds.</p>
              </div>
              <span style={{ position: 'absolute', top: 14, right: 16, fontSize: 15, color: 'rgba(245,240,232,0.4)' }}>→</span>
            </button>

            {/* Existing media — standalone creation path, distinct from Story's add-media */}
            <button
              onClick={onExistingMedia}
              style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.28)', padding: '0 0 32px', textAlign: 'center', animation: 'homeIn 0.4s ease 0.13s both' }}
            >
              Use photos &amp; videos I already have
            </button>
          </>
        )}
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// START A STORY — Step 1: Conversational prompt
// One open field. Story does the interpretation.
// ══════════════════════════════════════════════
const STORY_PROMPT_PLACEHOLDER = `We're hiking Tour du Mont Blanc for 8 days.

It's the two of us, through the Alps — from Chamonix, over the passes, and back.`

function ScreenStoryIntent({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [desc, setDesc] = useState(STORY_PROMPT_PLACEHOLDER)
  const [active, setActive] = useState(false)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  useEffect(() => { setActive(true) }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', padding: '56px 24px 36px', background: '#0a0a0b' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, marginBottom: 32, textAlign: 'left' }}>← Back</button>

        <h1 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 28, color: '#f5f0e8', lineHeight: 1.25, margin: '0 0 8px' }}>
          Tell me about<br />this experience.
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.32)', margin: '0 0 28px', lineHeight: 1.5 }}>
          What it is, how long, what you want it to feel like.
        </p>

        <textarea
          ref={textareaRef}
          value={desc}
          onChange={e => setDesc(e.target.value)}
          style={{
            flex: 1,
            width: '100%',
            borderRadius: 16,
            border: '1.5px solid rgba(245,240,232,0.1)',
            background: 'rgba(255,255,255,0.03)',
            color: '#f5f0e8',
            fontFamily: "'DM Sans', sans-serif",
            fontSize: 15, lineHeight: 1.7,
            padding: '18px 18px',
            resize: 'none',
            outline: 'none',
            boxSizing: 'border-box',
            marginBottom: 20,
          }}
        />

        <button
          onClick={onNext}
          disabled={!desc.trim()}
          style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: desc.trim() ? '#f5f0e8' : 'rgba(245,240,232,0.12)', color: desc.trim() ? '#0a0a0b' : 'rgba(245,240,232,0.25)', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: desc.trim() ? 'pointer' : 'default', transition: 'background 0.2s, color 0.2s' }}
        >
          Continue
        </button>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// START A STORY — Step 2: Creative Direction
// "How should this Story feel?" — persistent state.
// Alternative inputs: vibe preset · reference · text.
// None required. Establishes the kind of final Story.
// ══════════════════════════════════════════════
export type CreativeDirection = {
  vibe: string            // selected preset id ('' if none)
  tags: string[]          // qualitative descriptors
  description: string     // optional free-text
  reference: string | null // optional reference label
  music: MusicDirection   // inferred feeling of the music — not a track
}

// ══════════════════════════════════════════════
// MUSIC — Music Direction lives in the Creative Direction
// (a feeling, not a song). The actual track is picked at
// Create my Story, and changing it re-edits the Story.
// ══════════════════════════════════════════════
export type MusicDirection = {
  feel: string[]          // lightweight feel chips
  description: string     // optional free-text
  auto: boolean           // true = Story infers from the Creative Direction
}

const MUSIC_FEELS = ['Cinematic', 'Emotional', 'Epic', 'Dreamy', 'Energetic', 'Chill']

// Story's reading of the music, from vibe tags — shown, never configured.
function inferMusicLabel(direction: CreativeDirection): string {
  const m = direction.music
  if (!m.auto) {
    if (m.description) return m.description
    if (m.feel.length) return m.feel.join(' · ')
  }
  const t = direction.tags.map(x => x.toLowerCase())
  if (t.includes('energetic') || t.includes('kinetic')) return 'Energetic · driving rhythm'
  if (t.includes('intimate') || t.includes('personal')) return 'Warm acoustic · intimate'
  if (t.includes('minimal') || t.includes('quiet') || t.includes('calm')) return 'Ambient · calm and spacious'
  if (t.includes('playful')) return 'Upbeat · bright and playful'
  return 'Emotional cinematic · gradual build'
}

type MusicTrack = { id: string; title: string; mood: string; shape: string; duration: string; editNote: string; cover?: string; match?: RegExp }
const MUSIC_TRACKS: MusicTrack[] = [
  { id: 'alpine',  title: 'Alpine Journey',     mood: 'Cinematic · emotional',   shape: 'Gradual build', duration: '1:02', cover: IMG_ALPS_PANORAMA,   editNote: 'A patient opening — the peaks arrive with the build.' },
  { id: 'into',    title: 'Into the Mountains', mood: 'Epic · atmospheric',      shape: 'Strong climax', duration: '0:58', cover: IMG_MOUNTAIN_RIDGE,  match: /epic/, editNote: 'Bigger scale, a harder cut into the summit.' },
  { id: 'far',     title: 'Somewhere Far Away', mood: 'Dreamy · intimate',       shape: 'Gentle pacing', duration: '1:02', cover: IMG_COUPLE_HIKING,   match: /dreamy|intimate|acoustic|chill|calm|ambient/, editNote: 'More of you two, softer transitions, lingering moments.' },
  { id: 'forward', title: 'Moving Forward',     mood: 'Energetic · adventurous', shape: 'Faster pacing', duration: '0:55', cover: IMG_MOUNTAIN_TRAIL,  match: /energetic|driving|upbeat|playful/, editNote: 'Quicker cuts, more movement, the trail in motion.' },
]
// Create now — short city Stories get their own few recommendations.
const QUICK_TRACKS: MusicTrack[] = [
  { id: 'neon',   title: 'Neon Hours',  mood: 'Cinematic · moody',   shape: 'Slow build',    duration: '0:08', cover: IMG_NEON_STREET,        editNote: 'Wide and patient — the city reveals itself on the build.' },
  { id: 'pulse',  title: 'City Pulse',  mood: 'Energetic · kinetic', shape: 'Fast cuts',     duration: '0:08', cover: IMG_TIMES_SQUARE_CROWD, match: /energetic|driving|epic/, editNote: 'Quick cuts on the beat, the crowd in motion.' },
  { id: 'soft',   title: 'Soft Lights', mood: 'Calm · dreamy',       shape: 'Gentle pacing', duration: '0:10', cover: IMG_CITY_BOKEH,         match: /dreamy|calm|ambient|chill|intimate|acoustic/, editNote: 'Longer holds, soft light, room to breathe.' },
  { id: 'bright', title: 'Bright Side', mood: 'Playful · upbeat',    shape: 'Bouncy rhythm', duration: '0:08', cover: IMG_TIMES_SQUARE_SIGNS, match: /playful|upbeat/, editNote: 'Candid reactions, colour, a little more fun.' },
]

// Story picks a track that fits the direction — the user never has to.
function pickTrackFor(direction: CreativeDirection, tracks: MusicTrack[] = MUSIC_TRACKS): string {
  const label = inferMusicLabel(direction).toLowerCase()
  return (tracks.find(t => t.match?.test(label)) ?? tracks[0]).id
}

// Story Guide emphasis shaped by the overall feel — advice, not music logic.
function guideEmphasis(direction: CreativeDirection): string {
  const label = inferMusicLabel(direction).toLowerCase()
  if (/intimate|acoustic|dreamy|chill|calm|warm/.test(label))
    return 'For this Story: natural moments together, quiet pauses, laughter — and an ending that feels close.'
  if (/energetic|driving|faster/.test(label))
    return 'For this Story: lots of movement, quick moments on the trail, and energy right to the end.'
  return 'For this Story: one strong opening, movement through the landscape, the scale of it all — and one big moment.'
}

const EQ_STYLE = `@keyframes eqBar { from { transform: scaleY(0.25); } to { transform: scaleY(1); } }`

function EqBars({ playing, size = 14, color = '#d4a853' }: { playing: boolean; size?: number; color?: string }) {
  return (
    <span style={{ display: 'inline-flex', alignItems: 'flex-end', gap: 2, height: size, width: size }}>
      {[0.55, 1, 0.7, 0.85].map((h, i) => (
        <span key={i} style={{
          flex: 1, borderRadius: 1, background: color, height: `${h * 100}%`, transformOrigin: 'bottom',
          transform: playing ? undefined : 'scaleY(0.3)',
          animation: playing ? `eqBar 0.${6 + i}s ease-in-out ${i * 0.08}s infinite alternate` : 'none',
        }} />
      ))}
    </span>
  )
}

function PlayDot({ playing, onClick, size = 36 }: { playing: boolean; onClick: (e: React.MouseEvent) => void; size?: number }) {
  return (
    <button onClick={onClick} aria-label={playing ? 'Pause preview' : 'Play preview'} style={{ width: size, height: size, borderRadius: '50%', flexShrink: 0, cursor: 'pointer', background: playing ? 'rgba(212,168,83,0.14)' : 'rgba(245,240,232,0.06)', border: `1px solid ${playing ? 'rgba(212,168,83,0.45)' : 'rgba(245,240,232,0.14)'}`, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: 0 }}>
      {playing
        ? <EqBars playing size={12} />
        : <span style={{ width: 0, height: 0, borderTop: '5px solid transparent', borderBottom: '5px solid transparent', borderLeft: '8px solid #f5f0e8', marginLeft: 2 }} />}
    </button>
  )
}

// MUSIC on the Create screen — Story's pick, preview, change.
function MusicPick({ track, userPicked, onChangeMusic }: { track: MusicTrack; userPicked: boolean; onChangeMusic: () => void }) {
  const [previewing, setPreviewing] = useState(false)
  return (
    <div style={{ padding: '18px 0', borderTop: '1px solid rgba(245,240,232,0.07)', borderBottom: '1px solid rgba(245,240,232,0.07)', textAlign: 'left' }}>
      <style>{EQ_STYLE}</style>
      <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.25)', textTransform: 'uppercase', margin: '0 0 12px' }}>Music</p>
      <div style={{ display: 'flex', alignItems: 'center', gap: 14 }}>
        <PlayDot playing={previewing} onClick={() => setPreviewing(p => !p)} size={44} />
        <div style={{ flex: 1, minWidth: 0 }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: '0 0 2px' }}>♫ {userPicked ? 'Your pick' : "Story's pick"}</p>
          <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 19, color: '#f5f0e8', margin: 0, lineHeight: 1.2 }}>{track.title}</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.4)', margin: '3px 0 0' }}>{track.mood} · {track.shape} · {track.duration}</p>
        </div>
      </div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginTop: 14 }}>
        <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.28)' }}>{previewing ? 'Previewing…' : 'Your Story will be cut to this track.'}</span>
        <button onClick={() => { setPreviewing(false); onChangeMusic() }} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 12, color: '#d4a853', padding: 0 }}>Change music →</button>
      </div>
    </div>
  )
}

// Music Direction row — inferred feeling, optional Change →
function MusicDirectionRow({ direction, onChange }: { direction: CreativeDirection; onChange: () => void }) {
  return (
    <div style={{ display: 'flex', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12, padding: '14px 0', borderTop: '1px solid rgba(245,240,232,0.06)', borderBottom: '1px solid rgba(245,240,232,0.06)', textAlign: 'left' }}>
      <div style={{ minWidth: 0 }}>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.25)', textTransform: 'uppercase', margin: '0 0 5px' }}>♫ Music</p>
        <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 16, color: 'rgba(245,240,232,0.78)', margin: 0, lineHeight: 1.35 }}>{inferMusicLabel(direction)}</p>
      </div>
      <button onClick={onChange} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 12, color: '#d4a853', padding: 0, flexShrink: 0 }}>Change →</button>
    </div>
  )
}

// Inline sheet on the Creative Direction summary — lightweight, optional.
function MusicDirectionSheet({ direction, onClose, onSave }: { direction: CreativeDirection; onClose: () => void; onSave: (m: MusicDirection) => void }) {
  const [feel, setFeel] = useState<string[]>(direction.music.auto ? [] : direction.music.feel)
  const [desc, setDesc] = useState(direction.music.auto ? '' : direction.music.description)
  const toggle = (f: string) => setFeel(p => p.includes(f) ? p.filter(x => x !== f) : [...p, f])
  const has = feel.length > 0 || !!desc.trim()
  return (
    <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
      <div onClick={onClose} style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.6)', backdropFilter: 'blur(4px)' }} />
      <div style={{ position: 'relative', background: '#141416', borderTop: '1px solid rgba(245,240,232,0.07)', borderRadius: '22px 22px 0 0', padding: '22px 24px 36px', animation: 'sheetUp 0.3s ease both' }}>
        <style>{`@keyframes sheetUp { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: translateY(0); } }`}</style>
        <div style={{ width: 36, height: 4, borderRadius: 2, background: 'rgba(245,240,232,0.12)', margin: '0 auto 18px' }} />
        <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: '0 0 4px' }}>How should the music feel?</h3>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.35)', margin: '0 0 18px', lineHeight: 1.5 }}>Just the feeling — Story finds the track later.</p>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginBottom: 18 }}>
          {MUSIC_FEELS.map(f => {
            const on = feel.includes(f)
            return (
              <button key={f} onClick={() => toggle(f)} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, cursor: 'pointer', borderRadius: 50, padding: '8px 15px', color: on ? '#0a0a0b' : 'rgba(245,240,232,0.6)', background: on ? '#d4a853' : 'transparent', border: `1px solid ${on ? '#d4a853' : 'rgba(245,240,232,0.14)'}`, transition: 'all 0.2s' }}>{f}</button>
            )
          })}
        </div>
        <textarea value={desc} onChange={e => setDesc(e.target.value)} placeholder={'Describe it…\nEmotional cinematic music with a slow build, but not overly dramatic.'}
          style={{ width: '100%', borderRadius: 14, border: '1.5px solid rgba(245,240,232,0.1)', background: 'rgba(255,255,255,0.04)', color: '#f5f0e8', fontFamily: "'DM Sans', sans-serif", fontSize: 14, padding: '13px 15px', resize: 'none', height: 76, outline: 'none', boxSizing: 'border-box', marginBottom: 16 }} />
        <button disabled={!has} onClick={() => onSave({ feel, description: desc.trim(), auto: false })}
          style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: has ? '#f5f0e8' : 'rgba(245,240,232,0.12)', color: has ? '#0a0a0b' : 'rgba(245,240,232,0.25)', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: has ? 'pointer' : 'default', marginBottom: 8 }}>Done</button>
        <button onClick={() => onSave({ feel: [], description: '', auto: true })}
          style={{ width: '100%', padding: '11px 0', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.4)' }}>✦ Let Story choose</button>
      </div>
    </div>
  )
}

// CHOOSE MUSIC — a few strong recommendations, not a library.
function ScreenTMBMusic({ tracks, selectedId, fromResult, onSelect, onImport, onBack }: {
  tracks: MusicTrack[]; selectedId: string; fromResult: boolean
  onSelect: (id: string) => void; onImport: (name: string) => void; onBack: () => void
}) {
  const [active, setActive] = useState(false)
  const [playingId, setPlayingId] = useState<string | null>(null)
  const [pending, setPending] = useState(selectedId)
  const fileRef = useRef<HTMLInputElement>(null)
  useEffect(() => { setActive(true) }, [])
  const changed = pending !== selectedId

  return (
    <ScreenWrap active={active}>
      <style>{`${EQ_STYLE} @keyframes musicIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }`}</style>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0' }}>←</button>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 5px' }}>Choose music</p>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: 0 }}>Recommended for your Story</h2>
          </div>
        </div>

        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.36)', margin: '14px 20px 6px', lineHeight: 1.6 }}>
          Each track shapes a different edit — Story re-cuts the moments, pacing and build to fit.
        </p>

        <div style={{ padding: '6px 20px 0' }}>
          {tracks.map((t, i) => {
            const sel = pending === t.id
            const playing = playingId === t.id
            return (
              <div key={t.id} onClick={() => setPending(t.id)} style={{ display: 'flex', gap: 14, alignItems: 'flex-start', padding: '16px 14px', margin: '0 -14px', borderRadius: 16, cursor: 'pointer', background: sel ? 'rgba(212,168,83,0.06)' : 'transparent', border: `1px solid ${sel ? 'rgba(212,168,83,0.22)' : 'transparent'}`, transition: 'all 0.2s', animation: `musicIn 0.35s ease ${i * 0.05}s both` }}>
                <PlayDot playing={playing} onClick={e => { e.stopPropagation(); setPlayingId(playing ? null : t.id) }} />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
                    <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: 0 }}>{t.title}</p>
                    <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.3)', flexShrink: 0 }}>{t.duration}</span>
                  </div>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.5)', margin: '3px 0 0' }}>{t.mood}</p>
                  <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.32)', margin: '1px 0 0' }}>{t.shape}</p>
                  {sel && (
                    <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontStyle: 'italic', fontWeight: 300, fontSize: 13, color: 'rgba(245,240,232,0.45)', margin: '8px 0 0', lineHeight: 1.5 }}>{t.editNote}</p>
                  )}
                </div>
                {sel && <span style={{ fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 12, color: '#d4a853', flexShrink: 0, paddingTop: 4 }}>Selected ✓</span>}
              </div>
            )
          })}

          <input ref={fileRef} type="file" accept="audio/*" style={{ display: 'none' }}
            onChange={e => { const f = e.target.files?.[0]; if (f) { onImport(f.name.replace(/\.[^.]+$/, '')); setPending('imported') } e.target.value = '' }} />
          <button onClick={() => fileRef.current?.click()} style={{ marginTop: 10, background: 'none', border: 'none', cursor: 'pointer', padding: '10px 0', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.4)' }}>
            + Import music
          </button>
        </div>

        <div style={{ flex: 1 }} />
        <div style={{ padding: '20px 20px 44px' }}>
          {changed && fromResult && (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontStyle: 'italic', fontWeight: 300, fontSize: 15, color: 'rgba(245,240,232,0.55)', textAlign: 'center', margin: '0 0 14px', animation: 'musicIn 0.3s ease both' }}>
              Story may adjust the edit to fit this music.
            </p>
          )}
          <button onClick={() => changed ? onSelect(pending) : onBack()}
            style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer' }}>
            {changed ? (fromResult ? 'Re-edit with this music' : 'Use this music') : 'Done'}
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

const DIRECTION_PRESETS: { id: string; label: string; tags: string[] }[] = [
  { id: 'cinematic-journey',  label: 'Cinematic journey',  tags: ['Cinematic', 'Scenic', 'Journey'] },
  { id: 'energetic-adventure', label: 'Energetic adventure', tags: ['Energetic', 'Kinetic', 'Adventure'] },
  { id: 'personal-emotional', label: 'Personal & emotional', tags: ['Personal', 'Intimate', 'Emotional'] },
  { id: 'minimal-scenic',     label: 'Minimal / scenic',    tags: ['Minimal', 'Scenic', 'Quiet'] },
]

function ScreenStoryDirection({
  onNext, onBack, direction, setDirection,
}: {
  onNext: () => void
  onBack: () => void
  direction: CreativeDirection
  setDirection: (d: CreativeDirection) => void
}) {
  const [vibe, setVibe] = useState(direction.vibe)
  const [desc, setDesc] = useState(direction.description)
  const [reference, setReference] = useState<string | null>(direction.reference)
  const [active, setActive] = useState(false)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShown(true), 160)
    return () => clearTimeout(t)
  }, [])

  const hasInput = !!vibe || !!desc.trim() || !!reference

  const commit = () => {
    const preset = DIRECTION_PRESETS.find(p => p.id === vibe)
    setDirection({
      ...direction,
      vibe,
      tags: preset ? preset.tags : direction.tags,
      description: desc.trim(),
      reference,
    })
    onNext()
  }

  const fieldStyle: React.CSSProperties = {
    width: '100%', borderRadius: 12,
    border: '1.5px solid rgba(245,240,232,0.1)',
    background: 'rgba(255,255,255,0.03)',
    color: '#f5f0e8', fontFamily: "'DM Sans', sans-serif",
    fontSize: 14, lineHeight: 1.6, padding: '14px 15px',
    outline: 'none', boxSizing: 'border-box', resize: 'none',
  }

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes readIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0b', padding: '56px 24px 36px', overflowY: 'auto' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, marginBottom: 32, textAlign: 'left' }}>← Back</button>

        <h1 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 27, color: '#f5f0e8', lineHeight: 1.25, margin: '0 0 8px', animation: shown ? 'readIn 0.4s ease both' : 'none' }}>
          How should this<br />Story feel?
        </h1>
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.32)', margin: '0 0 26px', lineHeight: 1.5, animation: shown ? 'readIn 0.4s ease 0.05s both' : 'none' }}>
          Pick a feeling, add a reference, or describe it. Any one is enough.
        </p>

        {/* Vibe presets */}
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 10, marginBottom: 22, animation: shown ? 'readIn 0.4s ease 0.1s both' : 'none' }}>
          {DIRECTION_PRESETS.map(p => {
            const selected = vibe === p.id
            return (
              <button
                key={p.id}
                onClick={() => setVibe(selected ? '' : p.id)}
                style={{
                  position: 'relative', textAlign: 'left', cursor: 'pointer',
                  borderRadius: 14, padding: '16px 15px', minHeight: 84,
                  display: 'flex', flexDirection: 'column', justifyContent: 'flex-end',
                  background: selected ? 'rgba(212,168,83,0.08)' : 'rgba(255,255,255,0.03)',
                  border: selected ? '2px solid #d4a853' : '1.5px solid rgba(245,240,232,0.1)',
                  opacity: !vibe || selected ? 1 : 0.5, transition: 'all 0.2s',
                }}
              >
                {selected && (
                  <span style={{ position: 'absolute', top: 10, right: 10, width: 18, height: 18, borderRadius: 50, background: '#d4a853', color: '#0a0a0b', fontSize: 11, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', fontFamily: "'DM Sans', sans-serif" }}>✓</span>
                )}
                <span style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 17, color: '#f5f0e8', lineHeight: 1.2 }}>
                  {p.label}
                </span>
                <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.4)', marginTop: 5 }}>
                  {p.tags.join(' · ')}
                </span>
              </button>
            )
          })}
        </div>

        {/* Optional reference */}
        <div style={{ marginBottom: 18, animation: shown ? 'readIn 0.4s ease 0.15s both' : 'none' }}>
          {reference ? (
            <div style={{ display: 'flex', alignItems: 'center', gap: 12, borderRadius: 12, border: '1.5px solid rgba(245,240,232,0.12)', background: 'rgba(255,255,255,0.03)', padding: '12px 14px' }}>
              <div style={{ width: 40, height: 40, borderRadius: 8, background: 'rgba(212,168,83,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: 16, flexShrink: 0 }}>▶</div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: '#f5f0e8', margin: 0, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{reference}</p>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.35)', margin: '2px 0 0' }}>Reference video</p>
              </div>
              <button onClick={() => setReference(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.4)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, padding: 4 }}>✕</button>
            </div>
          ) : (
            <button
              onClick={() => setReference('Alps travel film.mp4')}
              style={{ width: '100%', borderRadius: 12, border: '1.5px dashed rgba(245,240,232,0.18)', background: 'transparent', color: 'rgba(245,240,232,0.45)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, padding: '14px 0', cursor: 'pointer' }}
            >
              + Add a reference
            </button>
          )}
        </div>

        {/* Optional free-text */}
        <div style={{ animation: shown ? 'readIn 0.4s ease 0.2s both' : 'none' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.3)', margin: '0 0 10px', letterSpacing: '0.04em' }}>
            or describe it
          </p>
          <textarea
            value={desc}
            onChange={e => setDesc(e.target.value)}
            placeholder={"Mostly landscapes and the scale of the mountains.\nInclude us naturally.\nSlow, cinematic feeling."}
            style={{ ...fieldStyle, height: 96 }}
          />
        </div>

        <div style={{ flex: 1, minHeight: 24 }} />

        <button
          onClick={commit}
          disabled={!hasInput}
          style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: hasInput ? '#f5f0e8' : 'rgba(245,240,232,0.12)', color: hasInput ? '#0a0a0b' : 'rgba(245,240,232,0.25)', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: hasInput ? 'pointer' : 'default', transition: 'background 0.2s, color 0.2s', animation: shown ? 'readIn 0.4s ease 0.25s both' : 'none' }}
        >
          Continue
        </button>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// START A STORY — Step 3: Story's interpretation
// Story shows what it understood + the direction it
// will hold onto. Correction routes back to Step 2.
// ══════════════════════════════════════════════
function ScreenStoryContext({ onNext, onBack, onEdit, direction, onMusicChange }: { onNext: () => void; onBack: () => void; onEdit: () => void; direction: CreativeDirection; onMusicChange: (m: MusicDirection) => void }) {
  const [musicOpen, setMusicOpen] = useState(false)
  const title = 'Tour du Mont Blanc'
  const experience = '8-day hiking trip'
  const [active, setActive] = useState(false)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShown(true), 160)
    return () => clearTimeout(t)
  }, [])

  const metaLine = direction.reference
    ? '~60-sec cinematic Story · with reference'
    : '~60-sec cinematic Story'

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes readIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', background: '#0a0a0b', padding: '56px 24px 36px', overflowY: 'auto' }}>
        <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, marginBottom: 32, textAlign: 'left' }}>← Back</button>

        {/* Story's reading framing */}
        <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.28)', margin: '0 0 20px', letterSpacing: '0.05em', animation: shown ? 'readIn 0.4s ease both' : 'none' }}>
          Here's what I understood.
        </p>

        {/* Experience summary */}
        <div style={{ marginBottom: 20, animation: shown ? 'readIn 0.4s ease 0.06s both' : 'none' }}>
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 26, color: '#f5f0e8', margin: '0 0 6px', lineHeight: 1.2 }}>
            {title}
          </h2>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.42)', margin: '0 0 2px' }}>
            {experience}
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.42)', margin: 0 }}>
            {metaLine}
          </p>
        </div>

        {/* Creative direction — the persistent tags */}
        <div style={{ display: 'flex', gap: 7, flexWrap: 'wrap', marginBottom: 22, animation: shown ? 'readIn 0.4s ease 0.11s both' : 'none' }}>
          {direction.tags.map(tag => (
            <span key={tag} style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.55)', background: 'rgba(212,168,83,0.08)', border: '1px solid rgba(212,168,83,0.22)', borderRadius: 50, padding: '5px 12px' }}>
              {tag}
            </span>
          ))}
        </div>

        {/* Music Direction — inferred feeling, optional to change */}
        <div style={{ marginBottom: 24, animation: shown ? 'readIn 0.4s ease 0.13s both' : 'none' }}>
          <MusicDirectionRow direction={direction} onChange={() => setMusicOpen(true)} />
        </div>

        {/* Creative direction — quoted back to user */}
        {direction.description && (
          <div style={{ borderLeft: '2px solid rgba(245,240,232,0.1)', paddingLeft: 14, marginBottom: 28, animation: shown ? 'readIn 0.4s ease 0.16s both' : 'none' }}>
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 16, color: 'rgba(245,240,232,0.55)', margin: 0, lineHeight: 1.6, whiteSpace: 'pre-line' }}>
              "{direction.description}"
            </p>
          </div>
        )}

        <div style={{ flex: 1, minHeight: 24 }} />

        {/* Primary — advance */}
        <button
          onClick={onNext}
          style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 10, animation: shown ? 'readIn 0.4s ease 0.2s both' : 'none' }}
        >
          Looks good
        </button>

        {/* Secondary — correction routes back to the direction step */}
        <button
          onClick={onEdit}
          style={{ width: '100%', padding: '13px 0', borderRadius: 50, background: 'transparent', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, border: 'none', cursor: 'pointer', animation: shown ? 'readIn 0.4s ease 0.24s both' : 'none' }}
        >
          Edit
        </button>
      </div>
      {musicOpen && <MusicDirectionSheet direction={direction} onClose={() => setMusicOpen(false)} onSave={m => { onMusicChange(m); setMusicOpen(false) }} />}
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// START A STORY — Step 3: Story Blueprint
// Visual creative arc — not a checklist
// ══════════════════════════════════════════════
function ScreenStoryBlueprint({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  const [active, setActive] = useState(false)
  const [shown, setShown] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShown(true), 200)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes chapterIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.08 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to bottom, rgba(10,10,11,0.88) 0%, rgba(10,10,11,0.7) 50%, rgba(10,10,11,0.95) 100%)' }} />

        <div style={{ position: 'relative', zIndex: 2, flex: 1, display: 'flex', flexDirection: 'column', padding: '56px 32px 40px', overflowY: 'auto' }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, marginBottom: 32, textAlign: 'left' }}>← Back</button>

          {/* Context label */}
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.22)', letterSpacing: '0.06em', margin: '0 0 8px', animation: shown ? 'chapterIn 0.4s ease both' : 'none' }}>
            Tour du Mont Blanc
          </p>

          {/* Primary heading — Story's intent, not a plan name */}
          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 26, color: '#f5f0e8', margin: '0 0 28px', lineHeight: 1.25, animation: shown ? 'chapterIn 0.4s ease 0.05s both' : 'none' }}>
            Here's what I'll look for.
          </h2>

          {/* Narrative arc — centered, connected by subtle ↓ */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start', marginBottom: 10 }}>
            {TMB_CHAPTERS.map((chapter, i) => {
              const isEdge = i === 0 || i === TMB_CHAPTERS.length - 1
              const delay = i * 0.06 + 0.1
              return (
                <div key={chapter.name} style={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-start' }}>
                  <div style={{ animation: shown ? `chapterIn 0.4s ease ${delay}s both` : 'none' }}>
                    <p style={{
                      fontFamily: "'Fraunces', Georgia, serif",
                      fontWeight: 300, fontStyle: 'italic',
                      fontSize: isEdge ? 19 : 15,
                      color: isEdge ? 'rgba(245,240,232,0.72)' : 'rgba(245,240,232,0.4)',
                      margin: '0 0 1px',
                    }}>
                      {chapter.name}
                    </p>
                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 11, fontStyle: 'italic',
                      color: isEdge ? 'rgba(245,240,232,0.22)' : 'rgba(245,240,232,0.15)',
                      margin: 0,
                    }}>
                      {chapter.note}
                    </p>
                  </div>
                  {i < TMB_CHAPTERS.length - 1 && (
                    <p style={{
                      fontFamily: "'DM Sans', sans-serif",
                      fontSize: 11,
                      color: 'rgba(245,240,232,0.14)',
                      margin: '5px 0 5px 2px', lineHeight: 1,
                      animation: shown ? `chapterIn 0.4s ease ${delay + 0.03}s both` : 'none',
                    }}>↓</p>
                  )}
                </div>
              )
            })}
          </div>

          {/* Permission for the Story to adapt */}
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontStyle: 'italic', fontSize: 13, color: 'rgba(245,240,232,0.25)', margin: '14px 0 0', lineHeight: 1.5, animation: shown ? `chapterIn 0.4s ease 0.52s both` : 'none' }}>
            This can change as your trip unfolds.
          </p>

          <div style={{ flex: 1 }} />

          {/* "All set" — below the arc, before the button */}
          <div style={{ marginBottom: 22, animation: shown ? `chapterIn 0.4s ease 0.56s both` : 'none' }}>
            <div style={{ width: 40, height: 1, background: 'rgba(245,240,232,0.08)', marginBottom: 20 }} />
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 20, color: 'rgba(245,240,232,0.82)', margin: '0 0 8px' }}>
              You're all set.
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.38)', margin: '0 0 4px', lineHeight: 1.6 }}>
              Capture naturally as you go.
            </p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.38)', margin: 0, lineHeight: 1.6 }}>
              I'll help when something would make your Story better.
            </p>
          </div>

          <button onClick={onNext} style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', animation: shown ? `chapterIn 0.4s ease 0.6s both` : 'none' }}>
            Start Story
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// START A STORY — Step 4: You're all set
// ══════════════════════════════════════════════
function ScreenStoryStart({ onStart, onBack }: { onStart: () => void; onBack: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 150)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, position: 'relative', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', background: '#0a0a0b', padding: '0 36px', overflow: 'hidden' }}>
        {/* Faint Alpine atmosphere */}
        <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.12 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.7)' }} />

        <button onClick={onBack} style={{ position: 'absolute', top: 52, left: 20, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, zIndex: 2 }}>← Back</button>

        <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center' }}>
          {/* Gold dot — quiet signal */}
          <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#d4a853', marginBottom: 24, opacity: show ? 1 : 0, transition: 'opacity 0.5s' }} />

          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 30, color: '#f5f0e8', margin: '0 0 18px', lineHeight: 1.2, opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.08s' }}>
            You're all set.
          </h2>

          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.48)', margin: '0 0 8px', lineHeight: 1.6, maxWidth: 270, opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.16s' }}>
            Capture naturally as you go.
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.48)', margin: '0 0 52px', lineHeight: 1.6, maxWidth: 270, opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.22s' }}>
            I'll help when something would make your Story better.
          </p>

          <button
            onClick={onStart}
            style={{ width: '100%', maxWidth: 310, padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.28s' }}
          >
            Start Story
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// TMB STORY HOME
// Persistent Story state — accumulates over time
// ══════════════════════════════════════════════
function ScreenTMB({
  tmbHasCapture,
  tmbJustStarted,
  onShootMoment,
  onShowMe,
  onHome,
  onViewMoments,
  moments,
  onCreateNow,
  onShootGuide,
  guideNote,
  completed,
  onComplete,
  onReopen,
  onEditDirection,
}: {
  guideNote?: string
  completed: boolean
  onComplete: () => void
  onReopen: () => void
  onEditDirection: () => void
  tmbHasCapture: boolean
  tmbJustStarted: boolean
  onShootMoment: () => void
  onShowMe: () => void
  onHome: () => void
  onViewMoments: () => void
  moments: MomentMedia[]
  onCreateNow: () => void
  onShootGuide: (category: string, shot: GuideShot) => void
}) {
  const [active, setActive] = useState(false)
  const [showMomentMsg, setShowMomentMsg] = useState(tmbHasCapture)
  const [menuOpen, setMenuOpen] = useState(false)
  const [confirm, setConfirm] = useState<'complete' | 'reopen' | null>(null)

  useEffect(() => {
    setActive(true)
    if (tmbHasCapture) {
      const t = setTimeout(() => setShowMomentMsg(false), 3600)
      return () => clearTimeout(t)
    }
  }, [tmbHasCapture])

  const showSuggestion = !tmbJustStarted && !completed

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes momentFade {
          0%   { opacity: 0; transform: translateY(-6px); }
          12%  { opacity: 1; transform: translateY(0); }
          72%  { opacity: 1; }
          100% { opacity: 0; }
        }
        @keyframes suggIn {
          from { opacity: 0; transform: translateY(8px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>

      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>

        {/* Header */}
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <button onClick={onHome} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.28)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
          <div>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: '0 0 3px', lineHeight: 1.2 }}>Tour du Mont Blanc</h2>
            {completed ? (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: '#d4a853', margin: 0, letterSpacing: '0.05em' }}>Completed</p>
            ) : (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.22)', margin: 0, letterSpacing: '0.05em' }}>{tmbJustStarted ? 'Day 1 of 8' : 'Day 3 of 8'}</p>
            )}
          </div>
          <button onClick={() => setMenuOpen(true)} aria-label="Story menu" style={{ marginLeft: 'auto', background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.4)', fontFamily: "'DM Sans', sans-serif", fontSize: 18, letterSpacing: '0.1em', padding: '0 0 0 12px', lineHeight: 1 }}>•••</button>
        </div>

        {/* Story qualitative state */}
        <div style={{ padding: '20px 20px 0' }}>
          {completed ? (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 17, color: 'rgba(245,240,232,0.7)', margin: 0, lineHeight: 1.4 }}>Everything from your trip, in one place.</p>
          ) : tmbJustStarted ? (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 17, color: 'rgba(245,240,232,0.7)', margin: 0, lineHeight: 1.4 }}>Your Story is ready to begin.</p>
          ) : tmbHasCapture ? (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 17, color: 'rgba(245,240,232,0.7)', margin: 0, lineHeight: 1.4 }}>Your Story is coming together.</p>
          ) : (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 17, color: 'rgba(245,240,232,0.7)', margin: 0, lineHeight: 1.4 }}>Your Story is taking shape.</p>
          )}
        </div>

        {/* Brief flash on return from capture */}
        {tmbHasCapture && showMomentMsg && (
          <div style={{ padding: '8px 20px 0' }}>
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 14, color: '#d4a853', margin: 0, animation: 'momentFade 3.6s ease forwards' }}>
              Perfect. That's a moment we were missing.
            </p>
          </div>
        )}

        {/* Mosaic — single tap target → Moments */}
        <div style={{ padding: '16px 20px 0' }}>
          {tmbJustStarted ? (
            <button
              onClick={onViewMoments}
              style={{ width: '100%', borderRadius: 14, background: 'rgba(245,240,232,0.03)', border: '1px dashed rgba(245,240,232,0.09)', aspectRatio: '16/5', display: 'flex', alignItems: 'center', justifyContent: 'center', cursor: 'pointer' }}
            >
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.18)', margin: 0 }}>Your moments will appear here</p>
            </button>
          ) : (
            <button
              onClick={onViewMoments}
              style={{ width: '100%', borderRadius: 14, overflow: 'hidden', position: 'relative', display: 'block', cursor: 'pointer', border: 'none', padding: 0 }}
            >
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
                {moments.slice(0, 6).map((m, i) => (
                  <div key={i} style={{ aspectRatio: '1', overflow: 'hidden', background: '#1a1a1c' }}>
                    <img src={m.src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.84 }} />
                  </div>
                ))}
              </div>
              <div style={{ position: 'absolute', bottom: 0, left: 0, right: 0, padding: '20px 12px 10px', background: 'linear-gradient(to top, rgba(10,10,11,0.68) 0%, transparent 100%)', display: 'flex', justifyContent: 'flex-end', alignItems: 'flex-end' }}>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.52)', margin: 0, letterSpacing: '0.02em' }}>{moments.length} moments →</p>
              </div>
            </button>
          )}
        </div>

        {/* Actions: PRIMARY solid + SECONDARY bare text */}
        <div style={{ padding: '20px 20px 0' }}>
          {completed ? (
            <button
              onClick={onCreateNow}
              style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer' }}
            >
              Create my Story
            </button>
          ) : (<>
          <button
            onClick={onShootMoment}
            style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 14 }}
          >
            Shoot a moment
          </button>
          <button
            onClick={onCreateNow}
            style={{ display: 'block', width: '100%', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.38)', padding: 0, textAlign: 'center' }}
          >
            Create my Story
          </button>
          </>)}
        </div>

        {/* Story Idea — passive, low-weight, no dismissal */}
        {showSuggestion && (
          <>
            <div style={{ margin: '24px 20px 0', borderTop: '1px solid rgba(245,240,232,0.06)' }} />
            <div style={{ margin: '20px 20px 0', animation: 'suggIn 0.4s ease both' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 10 }}>
                <span style={{ fontSize: 9, color: 'rgba(245,240,232,0.28)' }}>✦</span>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.25)', textTransform: 'uppercase', margin: 0 }}>Story Idea</p>
              </div>
              <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 16, color: 'rgba(245,240,232,0.72)', margin: '0 0 6px', lineHeight: 1.3 }}>
                A moment together
              </p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.28)', margin: '0 0 12px', lineHeight: 1.65 }}>
                You have beautiful landscapes. A moment together could add some warmth.
              </p>
              <button onClick={onShowMe} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontWeight: 500, fontSize: 13, color: 'rgba(245,240,232,0.4)', padding: 0 }}>
                Show me →
              </button>
            </div>
          </>
        )}

        {/* Story Guide — the moments that make this Story work, listed inline.
            A guide, not a checklist. ✓ = you have it, dashed ring = not yet.
            Each moment can be shot directly, with its own guidance. */}
        <div style={{ padding: '30px 20px 0' }}>
          <div style={{ borderTop: '1px solid rgba(245,240,232,0.06)', paddingTop: 20 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.25)', textTransform: 'uppercase', margin: '0 0 4px' }}>Story Guide</p>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontStyle: 'italic', fontSize: 13, color: 'rgba(245,240,232,0.3)', margin: 0, lineHeight: 1.5 }}>
              A guide, not a checklist — capture what feels right.
            </p>
            {guideNote && (
              <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 14, color: 'rgba(245,240,232,0.5)', margin: '10px 0 0', lineHeight: 1.55 }}>{guideNote}</p>
            )}
          </div>

          {TMB_STORY_GUIDE.map((cat) => (
            <div key={cat.id} style={{ marginTop: 22 }}>
              {/* Category header + advisory state */}
              <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', gap: 12, marginBottom: 3 }}>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: 0, lineHeight: 1.2 }}>{cat.title}</h3>
                <span style={{ display: 'flex', alignItems: 'center', gap: 6, flexShrink: 0 }}>
                  <span style={{ width: 4, height: 4, borderRadius: '50%', background: guideToneColor[cat.tone] }} />
                  <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: guideToneColor[cat.tone] }}>{cat.state}</span>
                </span>
              </div>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.35)', margin: '0 0 12px', lineHeight: 1.5 }}>{cat.intent}</p>

              {/* Moments — each with a coverage indicator and a direct Shoot */}
              {cat.items.map((item, j) => (
                <div key={j} style={{ display: 'flex', alignItems: 'center', gap: 11, padding: '9px 0', borderTop: '1px solid rgba(245,240,232,0.05)' }}>
                  {/* Coverage: ✓ when captured, dashed ring when not yet */}
                  {item.captured ? (
                    <span style={{ width: 18, height: 18, borderRadius: '50%', background: '#f5f0e8', color: '#0a0a0b', fontSize: 10, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, fontFamily: "'DM Sans', sans-serif" }}>✓</span>
                  ) : (
                    <span style={{ width: 18, height: 18, borderRadius: '50%', border: '1.5px dashed rgba(212,168,83,0.55)', flexShrink: 0 }} />
                  )}
                  <p style={{ flex: 1, minWidth: 0, fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: item.captured ? 'rgba(245,240,232,0.45)' : 'rgba(245,240,232,0.82)', margin: 0, lineHeight: 1.4 }}>
                    {item.label}
                  </p>
                  {!completed && <button
                    onClick={() => onShootGuide(cat.title, item.shot)}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', flexShrink: 0, fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 12, color: item.captured ? 'rgba(245,240,232,0.4)' : '#d4a853', padding: 0 }}
                  >
                    {item.captured ? 'Reshoot →' : 'Shoot →'}
                  </button>}
                </div>
              ))}
            </div>
          ))}
        </div>

        <div style={{ height: 40 }} />
      </div>
      {(menuOpen || confirm) && (
        <div style={{ position: 'absolute', inset: 0, zIndex: 20, display: 'flex', flexDirection: 'column', justifyContent: 'flex-end' }}>
          <style>{`@keyframes sheetUp { from { opacity: 0; transform: translateY(24px); } to { opacity: 1; transform: translateY(0); } }`}</style>
          <div onClick={() => { setMenuOpen(false); setConfirm(null) }} style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.6)', backdropFilter: 'blur(4px)' }} />
          <div style={{ position: 'relative', background: '#141416', borderTop: '1px solid rgba(245,240,232,0.07)', borderRadius: '22px 22px 0 0', padding: '22px 24px 36px', animation: 'sheetUp 0.3s ease both' }}>
            <div style={{ width: 36, height: 4, borderRadius: 2, background: 'rgba(245,240,232,0.12)', margin: '0 auto 14px' }} />
            {confirm ? (
              <>
                <h3 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: '6px 0 8px' }}>
                  {confirm === 'complete' ? 'Complete this Story?' : 'Reopen Tour du Mont Blanc?'}
                </h3>
                <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.45)', margin: '0 0 22px', lineHeight: 1.6 }}>
                  {confirm === 'complete'
                    ? 'Tour du Mont Blanc will move out of your active Stories. You can still view your Moments, create videos, or reopen it anytime.'
                    : 'This Story will return to your active Stories.'}
                </p>
                <button
                  onClick={() => { const c = confirm; setConfirm(null); c === 'complete' ? onComplete() : onReopen() }}
                  style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 8 }}
                >
                  {confirm === 'complete' ? 'Complete Story' : 'Reopen Story'}
                </button>
                <button onClick={() => setConfirm(null)} style={{ width: '100%', padding: '11px 0', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.4)' }}>Cancel</button>
              </>
            ) : (
              <>
                {[
                  { label: 'Edit Story details', onClick: () => setMenuOpen(false) },
                  { label: 'Creative direction', onClick: () => { setMenuOpen(false); onEditDirection() } },
                ].map(item => (
                  <button key={item.label} onClick={item.onClick} style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: '14px 0', fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.8)' }}>{item.label}</button>
                ))}
                <div style={{ borderTop: '1px solid rgba(245,240,232,0.07)', margin: '6px 0' }} />
                <button
                  onClick={() => { setMenuOpen(false); setConfirm(completed ? 'reopen' : 'complete') }}
                  style={{ display: 'block', width: '100%', textAlign: 'left', background: 'none', border: 'none', cursor: 'pointer', padding: '14px 0', fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: completed ? '#d4a853' : 'rgba(245,240,232,0.55)' }}
                >
                  {completed ? 'Reopen Story' : 'Complete Story'}
                </button>
              </>
            )}
          </div>
        </div>
      )}
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// TMB — Day 7: Story has plenty, no action needed
// ══════════════════════════════════════════════
function ScreenTMBLooked({ onHome, onReady, onCreate }: { onHome: () => void; onReady: () => void; onCreate: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <button onClick={onHome} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
          <div>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: '0 0 3px' }}>Tour du Mont Blanc</h2>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 11, color: 'rgba(245,240,232,0.22)', margin: 0, letterSpacing: '0.05em' }}>Day 7 of 8</p>
          </div>
        </div>

        {/* Updated mosaic — same images, reversed for variety */}
        <div style={{ margin: '16px 20px 0', borderRadius: 16, overflow: 'hidden', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
          {[...TMB_MOSAIC].reverse().map((src, i) => (
            <div key={i} style={{ aspectRatio: '1', overflow: 'hidden', background: '#1a1a1c' }}>
              <img src={src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.84 }} />
            </div>
          ))}
        </div>

        <div style={{ padding: '22px 20px 0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginBottom: 12, opacity: show ? 1 : 0, transition: 'opacity 0.45s' }}>
            <div style={{ width: 4, height: 4, borderRadius: '50%', background: 'rgba(245,240,232,0.18)', flexShrink: 0 }} />
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: 0 }}>Story</p>
          </div>
          <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 24, color: '#f5f0e8', margin: '0 0 10px', lineHeight: 1.3, opacity: show ? 1 : 0, transition: 'opacity 0.45s' }}>Looking good.</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.48)', margin: '0 0 4px', lineHeight: 1.7, opacity: show ? 1 : 0, transition: 'opacity 0.45s 0.1s' }}>You already have plenty for your Story.</p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.48)', margin: 0, lineHeight: 1.7, opacity: show ? 1 : 0, transition: 'opacity 0.45s 0.18s' }}>Enjoy the rest of your hike.</p>
        </div>

        <div style={{ flex: 1 }} />
        <div style={{ padding: '20px 20px 36px' }}>
          {/* Primary — create with confidence */}
          <button onClick={onCreate} style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 10, opacity: show ? 1 : 0, transition: 'opacity 0.45s 0.25s' }}>
            Create my Story
          </button>
          {/* Prototype nav — simulate end-of-trip state */}
          <button onClick={onReady} style={{ width: '100%', padding: '11px 0', borderRadius: 50, background: 'transparent', color: 'rgba(245,240,232,0.2)', fontFamily: "'DM Sans', sans-serif", fontSize: 13, border: 'none', cursor: 'pointer', opacity: show ? 1 : 0, transition: 'opacity 0.45s 0.3s' }}>
            End of trip →
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// TMB — Story is ready to create
// ══════════════════════════════════════════════
function ScreenTMBReady({ onCreate, onHome }: { onCreate: () => void; onHome: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 120)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.14 }} />
        <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.72)' }} />

        <button onClick={onHome} style={{ position: 'absolute', top: 52, left: 20, background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.28)', padding: 0, zIndex: 2 }}>← Back</button>

        <div style={{ position: 'relative', zIndex: 2, flex: 1, display: 'flex', flexDirection: 'column', justifyContent: 'center', padding: '0 32px' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, letterSpacing: '0.14em', color: '#d4a853', textTransform: 'uppercase', margin: '0 0 16px', opacity: show ? 1 : 0, transition: 'opacity 0.5s' }}>Tour du Mont Blanc</p>

          <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 30, color: '#f5f0e8', margin: '0 0 12px', lineHeight: 1.2, opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.08s' }}>
            Your Story is ready.
          </h2>

          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.42)', margin: '0 0 52px', lineHeight: 1.6, opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.14s' }}>
            Everything I need is here.
          </p>
        </div>

        <div style={{ position: 'relative', zIndex: 2, padding: '0 32px 44px' }}>
          <button onClick={onCreate} style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', opacity: show ? 1 : 0, transition: 'opacity 0.5s 0.26s' }}>
            Create my Story
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// ══════════════════════════════════════════════
// TMB — Shoot a moment: user-initiated scene read
// User sees something interesting; Story reads the
// scene and proposes an opportunistic shot.
// ══════════════════════════════════════════════
function ScreenTMBShootScene({ mode, guide, onNext, onBack }: { mode: 'shoot' | 'showme'; guide?: ShootGuide | null; onNext: () => void; onBack: () => void }) {
  const [active, setActive] = useState(false)
  const [phase, setPhase] = useState<'idle' | 'scanning' | 'done'>('idle')
  const [progress, setProgress] = useState(0)

  useEffect(() => { setActive(true) }, [])

  function startScan() {
    setPhase('scanning')
    setProgress(0)
    const start = Date.now()
    const duration = 2800
    const tick = () => {
      const p = Math.min((Date.now() - start) / duration, 1)
      setProgress(p)
      if (p < 1) requestAnimationFrame(tick)
      else { setPhase('done'); setTimeout(onNext, 320) }
    }
    requestAnimationFrame(tick)
  }

  const r = 36
  const circ = 2 * Math.PI * r

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          {phase === 'idle' && (
            <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
          )}
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 4px' }}>Tour du Mont Blanc</p>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: 0, lineHeight: 1.2 }}>
              {mode === 'showme' ? 'Show me' : 'Shoot a moment'}
            </h2>
            {guide && (
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: '#d4a853', margin: '4px 0 0' }}>
                Story Guide · {guide.category}
              </p>
            )}
          </div>
        </div>

        {/* Viewfinder area */}
        <div style={{ margin: '20px 20px 0', borderRadius: 20, overflow: 'hidden', aspectRatio: '4/3', position: 'relative', background: '#111114' }}>
          <img src={IMG_MOUNTAIN_TRAIL} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: phase === 'scanning' ? 0.72 : 0.52, transition: 'opacity 0.4s' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.35)' }} />
          <ViewfinderCorners color="rgba(245,240,232,0.25)" />
          {phase === 'scanning' && (
            <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(135deg, rgba(212,168,83,0.04) 0%, transparent 60%)', animation: 'none' }} />
          )}
        </div>

        {/* Instructions */}
        <div style={{ padding: '22px 20px 0', flex: 1 }}>
          {phase === 'idle' && (
            <>
              <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 20, color: 'rgba(245,240,232,0.85)', margin: '0 0 8px', lineHeight: 1.3 }}>
                {guide ? guide.shot.title : mode === 'showme' ? 'Show me where you are.' : 'What do you see right now?'}
              </p>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.3)', margin: 0, lineHeight: 1.65 }}>
                {guide
                  ? guide.shot.concept
                  : mode === 'showme'
                  ? 'I already know what I\'m looking for. Show me the scene and I\'ll find how to capture it here.'
                  : 'Show me the scene. I\'ll combine it with your Story to find a shot that fits.'}
              </p>
            </>
          )}
          {phase === 'scanning' && (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 17, color: 'rgba(245,240,232,0.6)', margin: 0, lineHeight: 1.4 }}>
              {mode === 'showme' ? 'Looking for the right moment…' : 'Taking in the scene…'}
            </p>
          )}
          {phase === 'done' && (
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontStyle: 'italic', fontSize: 17, color: '#d4a853', margin: 0 }}>Got it.</p>
          )}
        </div>

        {/* Scan button */}
        <div style={{ padding: '0 0 52px', display: 'flex', justifyContent: 'center' }}>
          {phase === 'idle' ? (
            <button
              onClick={startScan}
              style={{ width: 80, height: 80, borderRadius: '50%', background: 'rgba(245,240,232,0.1)', border: '2px solid rgba(245,240,232,0.25)', cursor: 'pointer', display: 'flex', alignItems: 'center', justifyContent: 'center' }}
            >
              <div style={{ width: 28, height: 28, borderRadius: '50%', background: '#f5f0e8', opacity: 0.85 }} />
            </button>
          ) : (
            <div style={{ position: 'relative', width: 80, height: 80 }}>
              <svg width="80" height="80" style={{ position: 'absolute', top: 0, left: 0, transform: 'rotate(-90deg)' }}>
                <circle cx="40" cy="40" r={r} fill="none" stroke="rgba(245,240,232,0.1)" strokeWidth="3" />
                <circle cx="40" cy="40" r={r} fill="none" stroke={phase === 'done' ? '#d4a853' : '#f5f0e8'} strokeWidth="3"
                  strokeDasharray={circ} strokeDashoffset={circ * (1 - progress)} style={{ transition: 'stroke 0.3s' }} />
              </svg>
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <div style={{ width: 28, height: 28, borderRadius: '50%', background: phase === 'done' ? '#d4a853' : 'rgba(245,240,232,0.7)', transition: 'background 0.3s' }} />
              </div>
            </div>
          )}
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// TMB — Shoot a moment: Story proposes a shot
// ══════════════════════════════════════════════
// STORY SHOOT — Thinking (Story-context-aware)
// Combines scene + Blueprint + existing moments
// ══════════════════════════════════════════════
function ScreenTMBShootThinking({ mode, onNext }: { mode: 'shoot' | 'showme'; onNext: () => void }) {
  const [active, setActive] = useState(false)
  const [phase, setPhase] = useState(0)
  useEffect(() => {
    setActive(true)
    const t1 = setTimeout(() => setPhase(1), 1000)
    const t2 = setTimeout(() => setPhase(2), 2200)
    const t3 = setTimeout(onNext, 3600)
    return () => { clearTimeout(t1); clearTimeout(t2); clearTimeout(t3) }
  }, [onNext])

  const lines = mode === 'showme'
    ? ['Reading the scene…', 'Looking for a moment together…', 'Found it.']
    : ['Reading the scene…', 'Matching it to your Story…', 'Finding the right moment…']

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes tmb-think-pulse {
          0%, 100% { opacity: 0.12; transform: scale(0.82); }
          50%       { opacity: 0.6;  transform: scale(1.12); }
        }
        @keyframes tmb-think-line {
          from { opacity: 0; transform: translateY(6px); }
          to   { opacity: 1; transform: translateY(0); }
        }
        @keyframes tmb-scene-fade {
          0%   { opacity: 0; }
          15%  { opacity: 1; }
          75%  { opacity: 1; }
          100% { opacity: 0; }
        }
      `}</style>
      <div style={{ flex: 1, position: 'relative', background: '#0a0a0b', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
        {/* Scene image fading out behind */}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          <img src={IMG_ALPS_PANORAMA} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', animation: 'tmb-scene-fade 3.6s ease forwards' }} />
          <div style={{ position: 'absolute', inset: 0, background: 'rgba(10,10,11,0.8)' }} />
        </div>

        <div style={{ position: 'relative', zIndex: 2, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 28 }}>
          <div style={{ display: 'flex', gap: 9 }}>
            {[0, 1, 2].map((i) => (
              <div key={i} style={{ width: 6, height: 6, borderRadius: '50%', background: '#f5f0e8', animation: `tmb-think-pulse 2s ease-in-out ${i * 0.3}s infinite` }} />
            ))}
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 10, alignItems: 'center' }}>
            {lines.slice(0, phase + 1).map((line, i) => (
              <p
                key={i}
                style={{
                  fontFamily: "'Fraunces', Georgia, serif",
                  fontWeight: 300,
                  fontStyle: 'italic',
                  fontSize: i === phase ? 20 : 14,
                  color: i === phase ? 'rgba(245,240,232,0.65)' : 'rgba(245,240,232,0.22)',
                  margin: 0,
                  textAlign: 'center',
                  animation: 'tmb-think-line 0.45s ease both',
                  transition: 'font-size 0.3s, color 0.3s',
                }}
              >
                {line}
              </p>
            ))}
          </div>
        </div>
      </div>
    </ScreenWrap>
  )
}

// Based on scene + Story context + existing material
// ══════════════════════════════════════════════
function ScreenTMBShootIdea({ mode, guide, onShoot, onTryAnother, onBack }: { mode: 'shoot' | 'showme'; guide?: ShootGuide | null; onShoot: () => void; onTryAnother: () => void; onBack: () => void }) {
  const [active, setActive] = useState(false)
  const [show, setShow] = useState(false)
  useEffect(() => {
    setActive(true)
    const t = setTimeout(() => setShow(true), 80)
    return () => clearTimeout(t)
  }, [])

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '4px 0 0' }}>Tour du Mont Blanc</p>
        </div>

        {/* Shot preview image */}
        <div style={{ margin: '18px 20px 0', borderRadius: 18, overflow: 'hidden', aspectRatio: '4/3', position: 'relative', background: '#111114', opacity: show ? 1 : 0, transition: 'opacity 0.4s' }}>
          <img src={IMG_ALPS_PANORAMA} alt="" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', objectFit: 'cover', opacity: 0.78 }} />
          <div style={{ position: 'absolute', inset: 0, background: 'linear-gradient(to top, rgba(10,10,11,0.7) 0%, transparent 50%)' }} />
          <div style={{ position: 'absolute', bottom: 14, left: 18, right: 18 }}>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.12em', color: 'rgba(245,240,232,0.45)', textTransform: 'uppercase', margin: '0 0 3px' }}>{guide ? `Story Guide · ${guide.category}` : 'Shot idea'}</p>
            <p style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 18, color: '#f5f0e8', margin: 0 }}>
              {guide ? guide.shot.title : mode === 'showme' ? 'A Moment Together' : 'The View From Here'}
            </p>
          </div>
        </div>

        {/* Concept description */}
        <div style={{ padding: '18px 20px 0', opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.08s' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 15, color: 'rgba(245,240,232,0.55)', margin: '0 0 10px', lineHeight: 1.65 }}>
            {guide
              ? guide.shot.concept
              : mode === 'showme'
              ? 'Walk together toward the ridge. Keep the mountains behind you — let the landscape frame the two of you.'
              : 'Pan slowly from the path up to the ridge. Let the scale of the mountains fill the frame.'}
          </p>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, color: 'rgba(245,240,232,0.28)', margin: 0, lineHeight: 1.6 }}>
            {guide
              ? guide.shot.note
              : mode === 'showme'
              ? '6 sec · Your Story has the landscape. This adds the human warmth — both of you, in that place.'
              : '8 sec · Your trail footage doesn\'t yet have scale. This would give the Story its sense of place.'}
          </p>
        </div>

        <div style={{ flex: 1 }} />

        {/* Actions */}
        <div style={{ padding: '0 20px 44px', opacity: show ? 1 : 0, transition: 'opacity 0.4s 0.14s' }}>
          <button
            onClick={onShoot}
            style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 10 }}
          >
            Let's shoot
          </button>
          {!guide && (
            <button
              onClick={onTryAnother}
              style={{ width: '100%', padding: '13px 0', borderRadius: 50, background: 'transparent', color: 'rgba(245,240,232,0.35)', fontFamily: "'DM Sans', sans-serif", fontSize: 14, border: '1px solid rgba(245,240,232,0.1)', cursor: 'pointer' }}
            >
              Try another idea
            </button>
          )}
        </div>
      </div>
    </ScreenWrap>
  )
}

// TMB — Create my Story: preview all Story media
// User verifies what Story has before generating
// ══════════════════════════════════════════════
function ScreenTMBPreview({ moments, onBack, onCreate, onAddMedia, track, userPicked, onChangeMusic }: { moments: MomentMedia[]; onBack: () => void; onCreate: () => void; onAddMedia: () => void; track: MusicTrack; userPicked: boolean; onChangeMusic: () => void }) {
  const [active, setActive] = useState(false)
  useEffect(() => { setActive(true) }, [])

  const allMedia = moments

  return (
    <ScreenWrap active={active}>
      <style>{`
        @keyframes previewIn {
          from { opacity: 0; transform: translateY(10px); }
          to   { opacity: 1; transform: translateY(0); }
        }
      `}</style>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflowY: 'auto' }}>

        {/* Header */}
        <div style={{ padding: '52px 20px 0', display: 'flex', alignItems: 'flex-start', gap: 12 }}>
          <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
          <div>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 10, letterSpacing: '0.13em', color: 'rgba(245,240,232,0.22)', textTransform: 'uppercase', margin: '0 0 5px' }}>Create your Story</p>
            <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: 0, lineHeight: 1.2 }}>Tour du Mont Blanc</h2>
          </div>
        </div>

        {/* Lead-in */}
        <div style={{ padding: '20px 20px 0', animation: 'previewIn 0.35s ease both' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.4)', margin: 0, lineHeight: 1.6 }}>Here's what I'm working with.</p>
        </div>

        {/* Media grid — 3-col, full-bleed within padding */}
        <div style={{ margin: '14px 20px 0', borderRadius: 14, overflow: 'hidden', display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2, animation: 'previewIn 0.38s ease 0.05s both' }}>
          {allMedia.map((m, i) => (
            <div key={i} style={{ aspectRatio: '1', overflow: 'hidden', background: '#1a1a1c', position: 'relative' }}>
              <img src={m.src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: 0.88 }} />
              {m.video && (
                <div style={{ position: 'absolute', bottom: 6, left: 7, width: 0, height: 0, borderTop: '4px solid transparent', borderBottom: '4px solid transparent', borderLeft: '7px solid rgba(245,240,232,0.85)' }} />
              )}
            </div>
          ))}
        </div>

        {/* Count */}
        <div style={{ padding: '12px 20px 0', animation: 'previewIn 0.38s ease 0.09s both' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.22)', margin: 0, letterSpacing: '0.04em' }}>{moments.length} moments</p>
        </div>

        {/* Reassurance */}
        <div style={{ padding: '14px 20px 0', animation: 'previewIn 0.38s ease 0.12s both' }}>
          <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.36)', margin: 0, lineHeight: 1.65 }}>
            Story will choose the moments that work best.
          </p>
        </div>

        {/* Music — Story's pick; the edit is built around it */}
        <div style={{ margin: '24px 20px 0', animation: 'previewIn 0.38s ease 0.14s both' }}>
          <MusicPick track={track} userPicked={userPicked} onChangeMusic={onChangeMusic} />
        </div>

        <div style={{ flex: 1 }} />

        {/* Actions */}
        <div style={{ padding: '24px 20px 44px', animation: 'previewIn 0.38s ease 0.15s both' }}>
          <button
            onClick={onCreate}
            style={{ width: '100%', padding: '17px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, border: 'none', cursor: 'pointer', marginBottom: 14 }}
          >
            Create my Story
          </button>
          <button
            onClick={onAddMedia}
            style={{ display: 'block', width: '100%', background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, color: 'rgba(245,240,232,0.32)', padding: 0, textAlign: 'center' }}
          >
            + Add photos or videos
          </button>
        </div>
      </div>
    </ScreenWrap>
  )
}

// ══════════════════════════════════════════════
// MOMENTS — lightweight management of the media the
// Story is considering. Preview, multi-select, and
// "Remove from Story" (never deletes from device).
// Add photos or videos ONLY adds media to Moments.
// ══════════════════════════════════════════════
function ScreenMoments({
  moments,
  onBack,
  onAddMedia,
  onRemove,
}: {
  moments: MomentMedia[]
  onBack: () => void
  onAddMedia: () => void
  onRemove: (ids: string[]) => void
}) {
  const [active, setActive] = useState(false)
  const [selectMode, setSelectMode] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [preview, setPreview] = useState<MomentMedia | null>(null)
  useEffect(() => { setActive(true) }, [])

  const toggle = (id: string) =>
    setSelected(prev => prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id])

  const exitSelect = () => { setSelectMode(false); setSelected([]) }

  const removeSelected = () => {
    if (selected.length === 0) return
    onRemove(selected)
    exitSelect()
  }

  const removeOne = (id: string) => {
    onRemove([id])
    setPreview(null)
  }

  return (
    <ScreenWrap active={active}>
      <div style={{ flex: 1, background: '#0a0a0b', display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
        {/* Header */}
        <div style={{ padding: '52px 20px 14px', display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', gap: 12, flexShrink: 0 }}>
          <div style={{ display: 'flex', alignItems: 'flex-start', gap: 12 }}>
            <button onClick={onBack} style={{ background: 'none', border: 'none', cursor: 'pointer', color: 'rgba(245,240,232,0.3)', fontFamily: "'DM Sans', sans-serif", fontSize: 15, padding: '2px 0 0', flexShrink: 0 }}>←</button>
            <div>
              <h2 style={{ fontFamily: "'Fraunces', Georgia, serif", fontWeight: 300, fontSize: 22, color: '#f5f0e8', margin: '0 0 3px', lineHeight: 1.2 }}>Moments</h2>
              <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.28)', margin: 0, letterSpacing: '0.04em' }}>
                {selectMode && selected.length > 0 ? `${selected.length} selected` : `${moments.length} moments`}
              </p>
            </div>
          </div>
          <button
            onClick={() => selectMode ? exitSelect() : setSelectMode(true)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 14, fontWeight: 500, color: 'rgba(245,240,232,0.5)', padding: '2px 0 0', flexShrink: 0 }}
          >
            {selectMode ? 'Cancel' : 'Select'}
          </button>
        </div>

        {/* Grid */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '0 20px' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
            {moments.map((m) => {
              const isSel = selected.includes(m.id)
              return (
                <div
                  key={m.id}
                  onClick={() => selectMode ? toggle(m.id) : setPreview(m)}
                  style={{ position: 'relative', aspectRatio: '1', overflow: 'hidden', background: '#1a1a1c', cursor: 'pointer' }}
                >
                  <img src={m.src} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover', opacity: isSel ? 0.5 : 0.86, transition: 'opacity 0.15s' }} />
                  {m.video && !isSel && (
                    <div style={{ position: 'absolute', bottom: 6, left: 7, width: 0, height: 0, borderTop: '4px solid transparent', borderBottom: '4px solid transparent', borderLeft: '7px solid rgba(245,240,232,0.85)' }} />
                  )}
                  {selectMode && (
                    <div style={{ position: 'absolute', top: 6, right: 6, width: 20, height: 20, borderRadius: '50%', background: isSel ? '#d4a853' : 'rgba(10,10,11,0.35)', border: isSel ? 'none' : '1.5px solid rgba(245,240,232,0.6)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                      {isSel && <span style={{ color: '#0a0a0b', fontSize: 11, fontWeight: 700, fontFamily: "'DM Sans', sans-serif" }}>✓</span>}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
          <div style={{ height: 20 }} />
        </div>

        {/* Bottom action */}
        <div style={{ padding: '14px 20px 40px', borderTop: '1px solid rgba(245,240,232,0.06)', flexShrink: 0 }}>
          {selectMode ? (
            <button
              onClick={removeSelected}
              disabled={selected.length === 0}
              style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: 'transparent', border: `1px solid ${selected.length > 0 ? 'rgba(212,168,83,0.5)' : 'rgba(245,240,232,0.1)'}`, cursor: selected.length > 0 ? 'pointer' : 'default', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, color: selected.length > 0 ? '#d4a853' : 'rgba(245,240,232,0.25)' }}
            >
              {selected.length > 0 ? `Remove from Story (${selected.length})` : 'Remove from Story'}
            </button>
          ) : (
            <button
              onClick={onAddMedia}
              style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: '#f5f0e8', color: '#0a0a0b', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15 }}
            >
              + Add photos or videos
            </button>
          )}
        </div>
      </div>

      {/* Lightweight preview */}
      {preview && (
        <div
          onClick={() => setPreview(null)}
          style={{ position: 'absolute', inset: 0, background: 'rgba(6,6,7,0.94)', zIndex: 30, display: 'flex', flexDirection: 'column' }}
        >
          <div style={{ padding: '52px 20px 0', display: 'flex', justifyContent: 'flex-end' }}>
            <button onClick={() => setPreview(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontSize: 22, color: 'rgba(245,240,232,0.6)', padding: 0, lineHeight: 1 }}>×</button>
          </div>
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '16px 20px' }} onClick={(e) => e.stopPropagation()}>
            <div style={{ position: 'relative', width: '100%', maxWidth: 340, borderRadius: 16, overflow: 'hidden', background: '#1a1a1c' }}>
              <img src={preview.src} alt="" style={{ width: '100%', display: 'block', objectFit: 'cover' }} />
              {preview.video && (
                <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <div style={{ width: 54, height: 54, borderRadius: '50%', background: 'rgba(10,10,11,0.5)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                    <div style={{ width: 0, height: 0, borderTop: '9px solid transparent', borderBottom: '9px solid transparent', borderLeft: '15px solid #f5f0e8', marginLeft: 4 }} />
                  </div>
                </div>
              )}
            </div>
          </div>
          <div style={{ padding: '0 20px 44px' }} onClick={(e) => e.stopPropagation()}>
            <button
              onClick={() => removeOne(preview.id)}
              style={{ width: '100%', padding: '15px 0', borderRadius: 50, background: 'transparent', border: '1px solid rgba(212,168,83,0.5)', cursor: 'pointer', fontFamily: "'DM Sans', sans-serif", fontWeight: 600, fontSize: 15, color: '#d4a853', marginBottom: 8 }}
            >
              Remove from Story
            </button>
            <p style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 12, color: 'rgba(245,240,232,0.3)', margin: 0, textAlign: 'center', lineHeight: 1.5 }}>
              Only removes it from this Story. Stays on your device.
            </p>
          </div>
        </div>
      )}
    </ScreenWrap>
  )
}

// ──────────────────────────────────────────────
// MAIN APP
// ──────────────────────────────────────────────
export default function App() {
  const [screen, setScreen] = useState<Screen>('home')
  const [selectedMedia, setSelectedMedia] = useState<string[]>([])
  // When true, user provided existing media that covers Shot 2 — only Shot 1 needed
  const [preMediaPath, setPreMediaPath] = useState(false)
  const [tmbCreated, setTmbCreated] = useState(false)
  // Lifecycle: organizational only — independent of any generated video.
  const [tmbCompleted, setTmbCompleted] = useState(false)
  const [tmbHasCapture, setTmbHasCapture] = useState(false)
  const [tmbJustStarted, setTmbJustStarted] = useState(false)
  const [tmbShootMode, setTmbShootMode] = useState<'shoot' | 'showme'>('shoot')
  const [mediaPickerReturn, setMediaPickerReturn] = useState<Screen>('idea')
  const [shootGuide, setShootGuide] = useState<ShootGuide | null>(null)
  // The media the Story is considering. "Add photos or videos" appends here;
  // "Remove from Story" filters it out. Never touches the device.
  const [moments, setMoments] = useState<MomentMedia[]>(INITIAL_MOMENTS)
  // 'add' = picker just adds to Moments and returns; 'analyze' = DIRECT pre-shoot flow.
  const [mediaMode, setMediaMode] = useState<'add' | 'analyze'>('analyze')
  // Persistent Creative Direction for the Story — set once during setup,
  // read wherever needed, never re-asked during Shoot / Guide / Idea / Create.
  const [creativeDirection, setCreativeDirection] = useState<CreativeDirection>({
    vibe: 'cinematic-journey',
    tags: ['Cinematic', 'Scenic', 'Journey'],
    description: 'Mostly landscapes and the feeling of the journey. Include us naturally.',
    reference: null,
    music: { feel: [], description: '', auto: true },
  })
  const go = (s: Screen) => setScreen(s)
  // Create now keeps its own lightweight direction (vibe → inferred music).
  const [quickDirection, setQuickDirection] = useState<CreativeDirection>({
    vibe: '', tags: ['Cinematic'], description: '', reference: null,
    music: { feel: [], description: '', auto: true },
  })
  // Which path is creating: persistent Story (TMB) or Create now.
  const [flow, setFlow] = useState<'tmb' | 'quick'>('quick')
  // Actual soundtrack per path — Story picks by default.
  const [trackIds, setTrackIds] = useState<{ tmb: string | null; quick: string | null }>({ tmb: null, quick: null })
  const [importedTrack, setImportedTrack] = useState<MusicTrack | null>(null)
  const [musicReturn, setMusicReturn] = useState<Screen>('tmbpreview')
  const [createMode, setCreateMode] = useState<'new' | 'reedit' | 'version'>('new')
  const trackFor = (f: 'tmb' | 'quick') => {
    const base = f === 'tmb' ? MUSIC_TRACKS : QUICK_TRACKS
    const list = importedTrack ? [...base, importedTrack] : base
    const id = trackIds[f] ?? pickTrackFor(f === 'tmb' ? creativeDirection : quickDirection, base)
    return { list, track: list.find(t => t.id === id) ?? base[0] }
  }
  const { list: tracks, track: activeTrack } = trackFor(flow)
  const startCreate = (f: 'tmb' | 'quick', mode: 'new' | 'reedit' | 'version' = 'new') => { setFlow(f); setCreateMode(mode); go('creating') }
  const openMusic = (f: 'tmb' | 'quick', returnTo: Screen) => { setFlow(f); setMusicReturn(returnTo); go('tmbmusic') }
  const openPicker = (returnTo: Screen) => { setMediaMode('analyze'); setMediaPickerReturn(returnTo); setSelectedMedia([]); go('premediapicker') }
  // Add media straight into Moments — no analysis, no Story ideas, no DIRECT.
  const openAddMedia = (returnTo: Screen) => { setMediaMode('add'); setMediaPickerReturn(returnTo); setSelectedMedia([]); go('premediapicker') }
  const addMomentsFromPicker = (ids: string[]) => {
    const added: MomentMedia[] = ids.map((id, i) => {
      const roll = CAMERA_ROLL.find(r => r.id === id)
      return { id: `add-${Date.now()}-${i}`, src: roll?.src ?? '', video: roll?.video ?? false }
    })
    setMoments(prev => [...prev, ...added])
  }

  const screenMap: Record<Screen, React.ReactNode> = {
    home: <ScreenHome
      tmbCreated={tmbCreated}
      tmbCompleted={tmbCompleted}
      momentCount={moments.length}
      onCreateNow={() => go('intent')}
      onStartStory={() => go('storyintent')}
      onExistingMedia={() => openPicker('home')}
      onTMB={() => go('tmb')}
    />,
    intent: <Screen1Intent
      direction={quickDirection}
      onMusicChange={m => { setQuickDirection({ ...quickDirection, music: m }); setTrackIds(prev => ({ ...prev, quick: null })) }}
      onNext={(vibe, description) => {
        const opt = styleOptions.find(o => o.id === vibe)
        setQuickDirection(d => ({ ...d, vibe: vibe ?? '', tags: opt ? [opt.label] : d.tags, description }))
        setTrackIds(prev => ({ ...prev, quick: null }))
        go('scene')
      }}
      onBack={() => go('home')}
    />,
    scene: <Screen3Scene onNext={() => go('thinking')} onBack={() => go('intent')} />,
    thinking: <Screen4Thinking onNext={() => go('idea')} />,
    idea: <Screen5Idea
      onNext={() => { setPreMediaPath(false); go('shot1') }}
      onAddExisting={() => openPicker('idea')}
      onBack={() => go('scene')}
    />,
    // Pre-shoot media flow
    premediapicker: <ScreenMediaPicker
      initialSelected={selectedMedia}
      onBack={() => go(mediaPickerReturn)}
      onDone={(ids) => {
        if (mediaMode === 'add') { addMomentsFromPicker(ids); go(mediaPickerReturn) }
        else { setSelectedMedia(ids); go('premediaanalysis') }
      }}
    />,
    premediaanalysis: <ScreenPreMediaAnalysis onDone={() => go('premediaresulta')} />,
    // Outcome A: existing clip replaces Shot 2 — only Shot 1 needed
    premediaresulta: <ScreenPreMediaResultA onShoot={() => { setPreMediaPath(true); go('shot1') }} />,
    // Outcome B: media helps but both shots still needed (prototype state, not primary path)
    premediaresultb: <ScreenPreMediaResultB onShoot={() => { setPreMediaPath(false); go('shot1') }} />,
    // Outcome C: existing media covers everything (prototype state, not primary path)
    premediaresultc: <ScreenPreMediaResultC onCreate={() => startCreate('quick')} />,
    shot1: (
      <ShotScreen
        shotNumber={1}
        totalShots={preMediaPath ? 1 : 2}
        instruction="Walk toward the signs."
        subInstruction="I'll follow behind."
        img={IMG_TIMES_SQUARE_CROWD}
        onReady={() => go('capture1')}
        onSkip={() => preMediaPath ? go('finalshot') : go('shot2')}
        onBack={() => go('idea')}
      />
    ),
    capture1: <CaptureScreen
      onDone={() => go('validation1')}
      onCancel={() => go('shot1')}
      hint="Follow behind"
      img={IMG_TIMES_SQUARE_CROWD}
    />,
    validation1: <Screen8Validation
      result="retry"
      reason="Someone crossed in front of you near the end."
      onNext={() => preMediaPath ? go('finalshot') : go('shot2')}
      onRetry={() => go('capture1')}
      onUseAnyway={() => preMediaPath ? go('finalshot') : go('shot2')}
    />,
    shot2: (
      <ShotScreen
        shotNumber={2}
        totalShots={2}
        instruction="Stop and look toward the lights."
        subInstruction="Hold for a moment."
        img={IMG_TIMES_SQUARE_SIGNS}
        onReady={() => go('capture2')}
        onSkip={() => startCreate('quick')}
        onBack={() => go('idea')}
      />
    ),
    capture2: <CaptureScreen
      onDone={() => go('finalshot')}
      onCancel={() => go('shot2')}
      hint="Hold still"
      img={IMG_TIMES_SQUARE_SIGNS}
    />,
    finalshot: <ScreenFinalCapture onCreateNow={() => startCreate('quick')}
      track={trackFor('quick').track} userPicked={trackIds.quick !== null}
      onChangeMusic={() => openMusic('quick', 'finalshot')} />,
    creating: <Screen10Creating key={createMode} onNext={() => go('result')} trackName={activeTrack.title} mode={createMode} />,
    result: <Screen11Result
      key={`${flow}-${activeTrack.id}-${createMode}`}
      onHome={() => go('home')}
      onRestart={() => startCreate(flow, 'version')}
      title={flow === 'tmb' ? 'Tour du Mont Blanc' : 'Your Story'}
      length={activeTrack.duration === '—' ? (flow === 'tmb' ? '~1 min' : '8 sec') : activeTrack.duration}
      image={activeTrack.cover ?? (flow === 'tmb' ? IMG_ALPS_PANORAMA : IMG_NEON_STREET)}
      trackName={activeTrack.title}
      onChangeMusic={() => openMusic(flow, 'result')}
    />,
    tmbmusic: <ScreenTMBMusic
      tracks={tracks}
      selectedId={activeTrack.id}
      fromResult={musicReturn === 'result'}
      key={flow}
      onBack={() => go(musicReturn)}
      onImport={name => setImportedTrack({ id: 'imported', title: name || 'Your track', mood: 'Imported', shape: 'Story will edit around it', duration: '—', editNote: 'Story will find the shape of your track and cut to it.' })}
      onSelect={id => {
        setTrackIds(prev => ({ ...prev, [flow]: id }))
        if (musicReturn === 'result') startCreate(flow, 'reedit'); else go(musicReturn)
      }}
    />,
    // ── Start a Story flow ──
    storyintent: <ScreenStoryIntent onNext={() => go('storydirection')} onBack={() => go('home')} />,
    storydirection: <ScreenStoryDirection
      onNext={() => go('storycontext')}
      onBack={() => go('storyintent')}
      direction={creativeDirection}
      setDirection={setCreativeDirection}
    />,
    storycontext: <ScreenStoryContext
      onNext={() => go('storyblueprint')}
      onBack={() => go('storydirection')}
      onEdit={() => go('storydirection')}
      direction={creativeDirection}
      onMusicChange={m => { setCreativeDirection({ ...creativeDirection, music: m }); setTrackIds(prev => ({ ...prev, tmb: null })) }}
    />,
    storyblueprint: <ScreenStoryBlueprint onNext={() => { setTmbCreated(true); setTmbJustStarted(true); go('tmb') }} onBack={() => go('storycontext')} />,
    storystart: <ScreenStoryStart onStart={() => { setTmbCreated(true); go('home') }} onBack={() => go('storyblueprint')} />,
    // ── TMB persistent story ──
    tmb: <ScreenTMB
      tmbHasCapture={tmbHasCapture}
      tmbJustStarted={tmbJustStarted}
      onShootMoment={() => { setTmbJustStarted(false); setShootGuide(null); setTmbShootMode('shoot'); go('tmbshootscene') }}
      onShowMe={() => { setTmbJustStarted(false); setShootGuide(null); setTmbShootMode('showme'); go('tmbshootscene') }}
      onHome={() => { setTmbJustStarted(false); go('home') }}
      onViewMoments={() => go('moments')}
      moments={moments}
      onCreateNow={() => go('tmbpreview')}
      guideNote={guideEmphasis(creativeDirection)}
      completed={tmbCompleted}
      onComplete={() => { setTmbCompleted(true); setTmbJustStarted(false); go('home') }}
      onReopen={() => setTmbCompleted(false)}
      onEditDirection={() => go('storycontext')}
      onShootGuide={(category, shot) => { setShootGuide({ category, shot }); setTmbShootMode('shoot'); go('tmbshootidea') }}
    />,
    moments: <ScreenMoments
      moments={moments}
      onBack={() => go('tmb')}
      onAddMedia={() => openAddMedia('moments')}
      onRemove={(ids) => setMoments(prev => prev.filter(m => !ids.includes(m.id)))}
    />,
    tmbshot: (
      <ShotScreen
        shotNumber={1}
        totalShots={1}
        instruction="Walk together toward the ridge."
        subInstruction="Keep the mountains behind you."
        duration="6 sec"
        skipLabel="Not now"
        img={IMG_COUPLE_HIKING}
        onReady={() => go('tmbcapture')}
        onSkip={() => go('tmb')}
        onBack={() => go('tmb')}
      />
    ),
    tmbcapture: <CaptureScreen
      onDone={() => go('tmbvalidated')}
      onCancel={() => go('tmbshot')}
      hint="Keep walking"
      img={IMG_COUPLE_HIKING}
    />,
    tmbvalidated: <Screen8Validation
      result="success"
      reason=""
      autoAdvance={true}
      onNext={() => { setTmbHasCapture(true); go('tmb') }}
      onRetry={() => go('tmbcapture')}
      onUseAnyway={() => { setTmbHasCapture(true); go('tmb') }}
    />,
    tmblooked: <ScreenTMBLooked onHome={() => go('tmb')} onReady={() => go('tmbready')} onCreate={() => go('tmbpreview')} />,
    tmbready: <ScreenTMBReady onCreate={() => go('tmbpreview')} onHome={() => go('tmb')} />,
    tmbpreview: <ScreenTMBPreview moments={moments} onBack={() => go('tmb')} onCreate={() => startCreate('tmb')} onAddMedia={() => openAddMedia('tmbpreview')}
      track={trackFor('tmb').track} userPicked={trackIds.tmb !== null} onChangeMusic={() => openMusic('tmb', 'tmbpreview')} />,
    // ── Shoot a moment (user-initiated) ──
    tmbshootscene: <ScreenTMBShootScene mode={tmbShootMode} guide={shootGuide} onNext={() => go('tmbshootthinking')} onBack={() => go('tmb')} />,
    tmbshootthinking: <ScreenTMBShootThinking mode={tmbShootMode} onNext={() => go('tmbshootidea')} />,
    tmbshootidea: <ScreenTMBShootIdea mode={tmbShootMode} guide={shootGuide} onShoot={() => shootGuide ? go('tmbshootcapture') : go('tmbshootshot')} onTryAnother={() => go('tmbshootidea')} onBack={() => shootGuide ? go('tmb') : go('tmbshootscene')} />,
    tmbshootshot: (
      <ShotScreen
        shotNumber={1}
        totalShots={1}
        instruction={shootGuide ? shootGuide.shot.title : tmbShootMode === 'showme' ? 'Walk together toward the ridge.' : 'Pan slowly from the path up to the ridge.'}
        subInstruction={shootGuide ? shootGuide.shot.concept : tmbShootMode === 'showme' ? 'Keep the mountains behind you.' : 'Let the mountains fill the frame.'}
        duration={shootGuide ? shootGuide.shot.note.split('·')[0].trim() : tmbShootMode === 'showme' ? '6 sec' : '8 sec'}
        skipLabel="Not now"
        img={tmbShootMode === 'showme' ? IMG_COUPLE_HIKING : IMG_ALPS_PANORAMA}
        onReady={() => go('tmbshootcapture')}
        onSkip={() => go('tmb')}
        onBack={() => go('tmbshootidea')}
      />
    ),
    tmbshootcapture: <CaptureScreen
      onDone={() => go('tmbvalidated')}
      onCancel={() => shootGuide ? go('tmbshootidea') : go('tmbshootshot')}
      hint={shootGuide ? shootGuide.shot.title : tmbShootMode === 'showme' ? 'Keep walking' : 'Pan slowly'}
      img={tmbShootMode === 'showme' ? IMG_COUPLE_HIKING : IMG_ALPS_PANORAMA}
    />,
  }

  return (
    <div
      style={{
        minHeight: '100svh',
        background: '#111112',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px 0',
        fontFamily: "'DM Sans', sans-serif",
      }}
    >
      {/* iPhone frame */}
      <div
        style={{
          position: 'relative',
          width: 390,
          height: 844,
          borderRadius: 52,
          background: '#0a0a0b',
          border: '1px solid rgba(255,255,255,0.06)',
          boxShadow: '0 40px 120px rgba(0,0,0,0.8), 0 0 0 1px rgba(255,255,255,0.04) inset',
          overflow: 'hidden',
        }}
      >
        {/* Status bar */}
        <div style={{ position: 'absolute', top: 0, left: 0, right: 0, height: 44, zIndex: 100, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 28px 0', pointerEvents: 'none' }}>
          <span style={{ fontFamily: "'DM Sans', sans-serif", fontSize: 13, fontWeight: 600, color: 'rgba(245,240,232,0.5)' }}>9:41</span>
          <div style={{ width: 120, height: 24, borderRadius: 20, background: 'rgba(0,0,0,0.6)', backdropFilter: 'blur(4px)' }} />
          <div style={{ display: 'flex', gap: 5, alignItems: 'center' }}>
            <span style={{ fontSize: 10, color: 'rgba(245,240,232,0.5)' }}>●●●</span>
          </div>
        </div>

        {/* Screens */}
        <div style={{ position: 'absolute', inset: 0 }}>
          {Object.entries(screenMap).map(([key, node]) => (
            <div
              key={key}
              style={{
                position: 'absolute',
                inset: 0,
                visibility: screen === key ? 'visible' : 'hidden',
                pointerEvents: screen === key ? 'auto' : 'none',
              }}
            >
              {screen === key ? node : null}
            </div>
          ))}
        </div>

        {/* Bottom home indicator */}
        <div style={{ position: 'absolute', bottom: 8, left: '50%', transform: 'translateX(-50%)', width: 120, height: 4, borderRadius: 2, background: 'rgba(245,240,232,0.2)', pointerEvents: 'none', zIndex: 100 }} />
      </div>
    </div>
  )
}
