# Architecture Decision Record (ADR-001) — Canvas Animation Loop Decoupling

## Status
Approved

## Context
In the development of the DUGOUT sports analytics war-room OS, we need to show a live telescopic top-down satellite tracking visualization of match actions, player movements, ball trajectories, and fielder chases. 

React's reconciliation cycle is declarative and operates on discrete state changes. However, frame-by-frame canvas animation requires continuous updates (60 frames per second). Driving these high-frequency renders using React state variables would cause:
1. React to re-evaluate and re-render the entire component tree 60 times per second.
2. Significant garbage collection overhead from creating short-lived state objects.
3. Severe main-thread blocking and frame drops (jank), deteriorating UI responsiveness and TTS speech coordination.

We require a highly optimized, responsive telemetry visualizer that operates at 60FPS on high-DPI screens without blocking browser interactions.

## Decision
We decided to decouple the frame-by-frame Canvas animation loop from React's reconciliation cycle using a **Decoupled Telemetry Ref-Buffer** pattern.

### Technical Implementation

1. **useRef Data Buffers**:
   All incoming high-level telemetry state frames (score updates, bowler stamina, shot polar angles, fielder positions, speech indicators) are stored in React `useRef` objects.

2. **Isolated requestAnimationFrame Loop**:
   A single frame-update loop is initialized using `requestAnimationFrame` inside a React `useEffect` block. This loop reads the latest telemetry directly from the refs on each frame, computing internal animation metrics (LERP coordinates, run-up paths, bat swings, particle velocities) completely independently of React's state.

3. **Hybrid Layered Presentation**:
   - **Canvas Layer**: Renders static field markings, player positions, ball paths, and particle physics.
   - **SVG/DOM Overlay Layer**: Renders high-tech HUD cards, orbital coordinates, scanlines, agent speech nodes, and sequential tickers using absolute-positioned HTML elements.
   - **Direct DOM Node Updates**: When an active AI agent speech spotlight is illuminated, the coordinate paths for the glowing neural data lines are calculated in the animation loop and pushed directly to the SVG line attributes (`x1`, `y1`, `x2`, `y2`) using vanilla JS element references. This bypasses React completely.

4. **Linear Interpolation (LERP)**:
   Instead of updating dot locations instantly, player coordinate steps are calculated using linear interpolation:
   $$x_{current} = x_{current} + (x_{target} - x_{current}) \times LERP\_RATE$$
   This ensures smooth visual movement over time.

5. **DPI & Resize Bounds**:
   Uses `ResizeObserver` on the wrapper card container to calculate layout bounds dynamically and applies `window.devicePixelRatio` scaling to eliminate graphics blur.

## Consequences

### Positive
- **60FPS Performance**: Eliminates React reconciliation overhead for visual animations. Main thread remains entirely free to handle user interactions and sequential Web Audio/Speech synthesis threads.
- **Zero React Re-Renders**: React only re-renders when high-level settings (e.g. show/hide satellite feed) change.
- **Dynamic Speed Scaling**: Animation phases compress and scale down dynamically matching simulation speed (1.5x, 2x, Turbo) without dropping frames.
- **SVG Styling Flexibility**: Overlay elements utilize standard GPU-accelerated CSS filters, glows, and animations.

### Negative
- **Manual Cleanup**: Requires careful management of event loop handles, observers, and canvas transformations to prevent memory leaks during component unmounting.
- **Ref State Sync**: Code must carefully update `useRef` buffers on every prop change to prevent the canvas loop from referencing stale state data.
