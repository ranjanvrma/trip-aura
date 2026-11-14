// The globe itself: renderer, meshes, input, render loop and clean-up. Framework-free so GlobeCanvas.tsx stays
// a thin React shell. Everything created here is disposed in dispose().

import * as THREE from "three";
import gsap from "gsap";
import { DEG, latLngToVec, shortestTurn } from "./geo";
import { subsolarPoint } from "./sun";
import type { LandData } from "./landMask";
import { MASK_HEIGHT, MASK_WIDTH } from "./landMask";
import { dotsFragment, dotsVertex, globeFragment, haloFragment, surfaceVertex } from "./shaders";

export interface Spot {
  lat: number;
  lng: number;
}

export interface GlobeScene {
  setTarget(target: Spot | null): void;
  setPins(pins: Spot[]): void;
  dispose(): void;
}

// Tuning. Colours are sRGB hex, as a designer would pick them.
const COLOR = {
  oceanCentre: 0x123448,
  oceanEdge: 0x081620,
  shallow: 0x1d5468,
  landLight: 0x4fbfa8,
  landDeep: 0x2b8273,
  coast: 0xa4f3e3,
  polar: 0xb7ccd4,
  atmosphere: 0x6fe3cf,
  dots: 0xd7fbf3,
  graticule: 0xffffff,
  target: 0xff8f66,
  pin: 0xf2c26b,
  pinRing: 0x0a0f14,
};
/** Night multiplier in linear light: roughly 40 percent darker on screen, shifted toward blue. */
const NIGHT = new THREE.Vector3(0.3, 0.34, 0.47);
/** Globe diameter as a share of the container's shorter side; the halo reaches about 0.89. */
const GLOBE_SCALE = 0.78;
const HALO_RADIUS = 1.14;
const FOV = 30;
const SPIN = (Math.PI * 2) / 90; // one turn per 90 s
const DEFAULT_TILT = 0.35; // shows a little more of the northern hemisphere, where most land is
const MAX_TILT = 1.0; // about 57 degrees either way
const RESUME_AFTER_MS = 3500; // auto-rotation comes back this long after a drag
const REFOCUS_AFTER_MS = 5000; // with a destination, the globe drifts back to it instead
const TURN_SECONDS = 1.4;

const clampTilt = (x: number) => Math.max(-MAX_TILT, Math.min(MAX_TILT, x));
const vec = (lat: number, lng: number, r = 1) => new THREE.Vector3(...latLngToVec(lat, lng, r));
const color = (hex: number) => new THREE.Color(hex);
const OUT = new THREE.Vector3(0, 0, 1);

/** Orients a marker group so its local +z points straight out of the surface at lat/lng. */
function placeOnSurface(obj: THREE.Object3D, lat: number, lng: number) {
  const n = vec(lat, lng);
  obj.position.copy(n);
  obj.quaternion.setFromUnitVectors(OUT, n);
}

export function createGlobeScene(
  host: HTMLElement,
  land: LandData | null,
  opts: { target: Spot | null; pins: Spot[]; reducedMotion: boolean; onReady: () => void },
): GlobeScene {
  const reduced = opts.reducedMotion;
  const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  const canvas = renderer.domElement;
  canvas.setAttribute("aria-hidden", "true");
  host.appendChild(canvas);

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(FOV, 1, 0.1, 50);
  const globe = new THREE.Group();
  scene.add(globe);

  // ---- land texture (a 1x1 sea texel if the data failed, so the globe still draws as ocean)
  const landTexture: THREE.Texture = land
    ? new THREE.CanvasTexture(land.canvas)
    : new THREE.DataTexture(new Uint8Array([0, 0, 0, 255]), 1, 1);
  landTexture.colorSpace = THREE.NoColorSpace; // a mask, not a colour
  landTexture.wrapS = THREE.RepeatWrapping; // longitude wraps, so filtering across the seam stays smooth
  landTexture.minFilter = THREE.LinearFilter; // no mipmaps: the shader's fract() at the seam would pick a tiny one
  landTexture.magFilter = THREE.LinearFilter;
  landTexture.generateMipmaps = false;
  landTexture.needsUpdate = true;

  const sun = new THREE.Vector3(0, 0, 1);

  // ---- globe body
  const globeMaterial = new THREE.ShaderMaterial({
    vertexShader: surfaceVertex,
    fragmentShader: globeFragment,
    uniforms: {
      uLand: { value: landTexture },
      uTexel: { value: new THREE.Vector2(1 / MASK_WIDTH, 1 / MASK_HEIGHT) },
      uSun: { value: sun },
      uNight: { value: NIGHT },
      uOceanCentre: { value: color(COLOR.oceanCentre) },
      uOceanEdge: { value: color(COLOR.oceanEdge) },
      uShallow: { value: color(COLOR.shallow) },
      uLandLight: { value: color(COLOR.landLight) },
      uLandDeep: { value: color(COLOR.landDeep) },
      uCoast: { value: color(COLOR.coast) },
      uPolar: { value: color(COLOR.polar) },
      uAtmosphere: { value: color(COLOR.atmosphere) },
    },
  });
  globe.add(new THREE.Mesh(new THREE.SphereGeometry(1, 96, 64), globeMaterial));

  // ---- land dots: a fine stipple that keeps the land from looking like flat clip art
  const dotsMaterial = new THREE.ShaderMaterial({
    vertexShader: dotsVertex,
    fragmentShader: dotsFragment,
    transparent: true,
    depthWrite: false,
    uniforms: {
      uSize: { value: 3 },
      uSun: { value: sun },
      uNight: { value: NIGHT },
      uColor: { value: color(COLOR.dots) },
      uOpacity: { value: 0.5 },
    },
  });
  if (land && land.dots.length) {
    const g = new THREE.BufferGeometry();
    // 1.003 keeps the dots just above the surface so the depth test never flickers between them
    const lifted = land.dots.map((v) => v * 1.003);
    g.setAttribute("position", new THREE.BufferAttribute(lifted, 3));
    globe.add(new THREE.Points(g, dotsMaterial));
  }

  // ---- graticule every 30 degrees
  const grid: THREE.Vector3[] = [];
  const STEPS = 96;
  for (const lat of [-60, -30, 0, 30, 60]) {
    for (let i = 0; i < STEPS; i++) {
      grid.push(vec(lat, (i / STEPS) * 360 - 180, 1.0015), vec(lat, ((i + 1) / STEPS) * 360 - 180, 1.0015));
    }
  }
  for (let lng = -180; lng < 180; lng += 30) {
    for (let i = 0; i < STEPS / 2; i++) {
      const a = -80 + (i / (STEPS / 2)) * 160;
      const b = -80 + ((i + 1) / (STEPS / 2)) * 160;
      grid.push(vec(a, lng, 1.0015), vec(b, lng, 1.0015));
    }
  }
  const gridMaterial = new THREE.LineBasicMaterial({
    color: COLOR.graticule, transparent: true, opacity: 0.1, depthWrite: false,
  });
  globe.add(new THREE.LineSegments(new THREE.BufferGeometry().setFromPoints(grid), gridMaterial));

  // ---- atmosphere halo (rotation-independent, so it sits on the scene, not the globe)
  const haloMaterial = new THREE.ShaderMaterial({
    vertexShader: surfaceVertex,
    fragmentShader: haloFragment,
    side: THREE.BackSide,
    transparent: true,
    depthWrite: false,
    uniforms: { uColor: { value: color(COLOR.atmosphere) }, uStrength: { value: 0.5 } },
  });
  scene.add(new THREE.Mesh(new THREE.SphereGeometry(HALO_RADIUS, 64, 48), haloMaterial));

  // ---- destination marker: base dot, short stem, head, pulsing ring
  const targetMaterial = new THREE.MeshBasicMaterial({ color: COLOR.target });
  const pulseMaterial = new THREE.MeshBasicMaterial({
    color: COLOR.target, transparent: true, opacity: 0.6, depthWrite: false, side: THREE.DoubleSide,
  });
  const marker = new THREE.Group();
  const base = new THREE.Mesh(new THREE.CircleGeometry(0.012, 24), targetMaterial);
  base.position.z = 0.002;
  const stemGeometry = new THREE.CylinderGeometry(0.0035, 0.0035, 0.07, 8);
  stemGeometry.rotateX(Math.PI / 2); // cylinders stand on y; the marker's "up" is +z
  const stem = new THREE.Mesh(stemGeometry, targetMaterial);
  stem.position.z = 0.035;
  const head = new THREE.Mesh(new THREE.SphereGeometry(0.02, 20, 14), targetMaterial);
  head.position.z = 0.075;
  const pulse = new THREE.Mesh(new THREE.RingGeometry(0.022, 0.03, 48), pulseMaterial);
  pulse.position.z = 0.003;
  pulse.visible = !reduced;
  marker.add(base, stem, head, pulse);
  marker.visible = false;
  globe.add(marker);

  // ---- saved-trip pins share one geometry and material pair
  const pinGeometry = new THREE.CircleGeometry(0.014, 20);
  const pinRingGeometry = new THREE.RingGeometry(0.014, 0.02, 28);
  const pinMaterial = new THREE.MeshBasicMaterial({ color: COLOR.pin });
  const pinRingMaterial = new THREE.MeshBasicMaterial({ color: COLOR.pinRing });
  const pinLayer = new THREE.Group();
  globe.add(pinLayer);

  // ---- great-circle arc from the first saved trip to the destination
  const arcMaterial = new THREE.MeshBasicMaterial({ color: COLOR.target, transparent: true, opacity: 0.8 });
  let arc: THREE.Mesh | null = null;

  // ---- state
  let target: Spot | null = null;
  let pins: Spot[] = [];
  let dirty = true;
  let visible = true;
  let lost = false;
  let raf = 0;
  let spin = reduced ? 0 : 1; // 0..1, ramps up so auto-rotation eases back in
  let velX = 0;
  let velY = 0;
  let dragging = false;
  let pointerId = -1;
  let lastX = 0;
  let lastY = 0;
  let lastT = 0;
  let releasedAt = -Infinity;
  let refocusPending = false;
  let dragScale = 0.01; // radians per CSS pixel, set on resize
  let renderedX = NaN;
  let renderedY = NaN;
  const timer = new THREE.Timer();

  function rebuildArc() {
    if (arc) {
      globe.remove(arc);
      arc.geometry.dispose();
      arc = null;
    }
    const from = pins[0];
    if (!target || !from) return;
    const a = vec(from.lat, from.lng);
    const b = vec(target.lat, target.lng);
    const angle = a.angleTo(b);
    if (angle < 0.01) return;
    const lift = 0.02 + 0.1 * (angle / Math.PI); // longer flights arc higher, but stay close to the surface
    const points: THREE.Vector3[] = [];
    const SEGMENTS = 64;
    for (let i = 0; i <= SEGMENTS; i++) {
      const t = i / SEGMENTS;
      // spherical interpolation keeps the path on the great circle
      const p = a.clone().multiplyScalar(Math.sin((1 - t) * angle))
        .add(b.clone().multiplyScalar(Math.sin(t * angle)))
        .divideScalar(Math.sin(angle));
      points.push(p.setLength(1.004 + lift * Math.sin(Math.PI * t)));
    }
    arc = new THREE.Mesh(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(points), SEGMENTS, 0.0028, 6, false), arcMaterial);
    globe.add(arc);
    dirty = true;
  }

  function faceTarget(instant: boolean) {
    if (!target) return;
    const y = globe.rotation.y;
    const toY = y + shortestTurn(y, -target.lng * DEG);
    const toX = clampTilt(target.lat * DEG);
    if (instant || reduced) {
      gsap.killTweensOf(globe.rotation);
      globe.rotation.x = toX;
      globe.rotation.y = toY;
      dirty = true;
      return;
    }
    gsap.to(globe.rotation, { x: toX, y: toY, duration: TURN_SECONDS, ease: "power3.inOut", overwrite: true });
    start();
  }

  function updateSun() {
    const s = subsolarPoint(new Date());
    sun.copy(vec(s.lat, s.lng));
    dirty = true;
  }

  function resize() {
    const { width, height } = host.getBoundingClientRect();
    if (width < 1 || height < 1) return;
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    // Distance at which the sphere's silhouette spans GLOBE_SCALE of the shorter side, for either orientation.
    const halfV = (FOV / 2) * DEG;
    const halfShort = Math.min(halfV, Math.atan(Math.tan(halfV) * camera.aspect));
    const silhouette = Math.atan(GLOBE_SCALE * Math.tan(halfShort));
    camera.position.set(0, 0, 1 / Math.sin(silhouette));
    camera.updateProjectionMatrix();
    const diameter = GLOBE_SCALE * Math.min(width, height);
    dragScale = Math.PI / diameter; // dragging across the globe turns it half a turn, so land follows the pointer
    dotsMaterial.uniforms.uSize.value = Math.max(1.5, diameter * 0.0042) * renderer.getPixelRatio();
    dirty = true;
    start();
  }

  function step(dt: number, now: number) {
    const r = globe.rotation;
    if (!dragging) {
      if (Math.abs(velX) + Math.abs(velY) > 1e-4) {
        r.y += velY * dt;
        r.x = clampTilt(r.x + velX * dt);
        const decay = Math.exp(-dt * 3.2);
        velX *= decay;
        velY *= decay;
      }
      const idle = now - releasedAt;
      const tweening = gsap.isTweening(r);
      if (!target && !reduced && !tweening && idle > RESUME_AFTER_MS) {
        spin = Math.min(1, spin + dt / 1.5);
        r.y += SPIN * spin * dt;
        r.x += (DEFAULT_TILT - r.x) * Math.min(1, dt * 0.5);
      }
      if (target && refocusPending && idle > REFOCUS_AFTER_MS) {
        refocusPending = false;
        faceTarget(false);
      }
      if (!tweening && Math.abs(r.y) > Math.PI) r.y -= Math.sign(r.y) * Math.PI * 2; // keep the angle small
    }
    if (marker.visible && !reduced) {
      const phase = (timer.getElapsed() % 2.2) / 2.2;
      pulse.scale.setScalar(1 + 1.8 * (1 - (1 - phase) * (1 - phase)));
      pulseMaterial.opacity = 0.6 * (1 - phase);
      dirty = true;
    }
  }

  function frame(t: number) {
    raf = requestAnimationFrame(frame);
    timer.update(t);
    step(Math.min(timer.getDelta(), 0.1), performance.now());
    const { x, y } = globe.rotation;
    if (dirty || x !== renderedX || y !== renderedY) {
      renderer.render(scene, camera);
      renderedX = x;
      renderedY = y;
      dirty = false;
    }
  }

  function start() {
    if (raf || !visible || lost || document.hidden) return;
    timer.reset();
    raf = requestAnimationFrame(frame);
  }

  function stop() {
    cancelAnimationFrame(raf);
    raf = 0;
  }

  // ---- input: drag to turn (mouse and touch); touch-action: pan-y in CSS leaves vertical swipes to the page
  const onDown = (e: PointerEvent) => {
    if (e.pointerType === "mouse" && e.button !== 0) return;
    dragging = true;
    pointerId = e.pointerId;
    host.setPointerCapture(e.pointerId);
    host.classList.add("is-dragging");
    lastX = e.clientX;
    lastY = e.clientY;
    lastT = e.timeStamp;
    velX = 0;
    velY = 0;
    spin = 0;
    gsap.killTweensOf(globe.rotation);
    start();
  };
  const onMove = (e: PointerEvent) => {
    if (!dragging || e.pointerId !== pointerId) return;
    const dx = (e.clientX - lastX) * dragScale;
    const dy = (e.clientY - lastY) * dragScale;
    const dt = Math.max(e.timeStamp - lastT, 1) / 1000;
    globe.rotation.y += dx;
    globe.rotation.x = clampTilt(globe.rotation.x + dy);
    // smoothed velocity for the throw on release, capped so a flick cannot spin it wildly
    velY = Math.max(-6, Math.min(6, velY * 0.6 + (dx / dt) * 0.4));
    velX = Math.max(-6, Math.min(6, velX * 0.6 + (dy / dt) * 0.4));
    lastX = e.clientX;
    lastY = e.clientY;
    lastT = e.timeStamp;
  };
  const onUp = (e: PointerEvent) => {
    if (!dragging || e.pointerId !== pointerId) return;
    dragging = false;
    host.classList.remove("is-dragging");
    if (host.hasPointerCapture(e.pointerId)) host.releasePointerCapture(e.pointerId);
    // no throw if the pointer rested before letting go, or if the visitor asked for less motion
    if (reduced || e.timeStamp - lastT > 80) {
      velX = 0;
      velY = 0;
    }
    releasedAt = performance.now();
    refocusPending = !!target;
  };
  host.addEventListener("pointerdown", onDown);
  host.addEventListener("pointermove", onMove);
  host.addEventListener("pointerup", onUp);
  host.addEventListener("pointercancel", onUp);

  // ---- lifecycle: draw only while on screen and the tab is visible; survive a lost GPU context
  const io = new IntersectionObserver(([entry]) => {
    visible = entry.isIntersecting;
    if (visible) start(); else stop();
  });
  io.observe(host);
  const ro = new ResizeObserver(resize);
  ro.observe(host);
  const onVisibility = () => {
    if (document.hidden) stop();
    else {
      updateSun();
      start();
    }
  };
  document.addEventListener("visibilitychange", onVisibility);
  const onLost = (e: Event) => {
    e.preventDefault(); // tells the browser we will handle a restore
    lost = true;
    stop();
  };
  const onRestored = () => {
    lost = false;
    landTexture.needsUpdate = true;
    dirty = true;
    start();
  };
  canvas.addEventListener("webglcontextlost", onLost);
  canvas.addEventListener("webglcontextrestored", onRestored);
  const sunTimer = window.setInterval(updateSun, 60_000);

  // ---- public API
  function setTarget(next: Spot | null) {
    target = next ? { lat: next.lat, lng: next.lng } : null;
    refocusPending = false;
    if (target) {
      placeOnSurface(marker, target.lat, target.lng);
      marker.visible = true;
      spin = 0;
      faceTarget(false);
    } else {
      marker.visible = false;
      releasedAt = -Infinity; // resume turning straight away (spin ramps up from 0)
    }
    rebuildArc();
    dirty = true;
    start();
  }

  function setPins(next: Spot[]) {
    pins = next.map((p) => ({ lat: p.lat, lng: p.lng }));
    pinLayer.clear();
    for (const p of pins) {
      const g = new THREE.Group();
      const ring = new THREE.Mesh(pinRingGeometry, pinRingMaterial);
      ring.position.z = 0.0022;
      const dot = new THREE.Mesh(pinGeometry, pinMaterial);
      dot.position.z = 0.0026;
      g.add(ring, dot);
      placeOnSurface(g, p.lat, p.lng);
      pinLayer.add(g);
    }
    rebuildArc();
    dirty = true;
    start();
  }

  // ---- first frame
  // Start facing roughly the visitor's own longitude (from the browser's time zone), tilted a little north.
  globe.rotation.x = DEFAULT_TILT;
  globe.rotation.y = (new Date().getTimezoneOffset() / 4) * DEG; // offset minutes / 4 = -longitude degrees
  updateSun();
  setPins(opts.pins);
  if (opts.target) {
    setTarget(opts.target);
    faceTarget(true);
  }
  resize();
  renderer.render(scene, camera);
  renderedX = globe.rotation.x;
  renderedY = globe.rotation.y;
  dirty = false;
  const readyFrame = requestAnimationFrame(() => opts.onReady());

  return {
    setTarget,
    setPins,
    dispose() {
      stop();
      cancelAnimationFrame(readyFrame);
      window.clearInterval(sunTimer);
      gsap.killTweensOf(globe.rotation);
      io.disconnect();
      ro.disconnect();
      document.removeEventListener("visibilitychange", onVisibility);
      host.removeEventListener("pointerdown", onDown);
      host.removeEventListener("pointermove", onMove);
      host.removeEventListener("pointerup", onUp);
      host.removeEventListener("pointercancel", onUp);
      host.classList.remove("is-dragging");
      canvas.removeEventListener("webglcontextlost", onLost);
      canvas.removeEventListener("webglcontextrestored", onRestored);
      arc?.geometry.dispose();
      scene.traverse((o) => {
        if (o instanceof THREE.Mesh || o instanceof THREE.Points || o instanceof THREE.LineSegments) {
          o.geometry.dispose();
          const m = o.material as THREE.Material | THREE.Material[];
          if (Array.isArray(m)) m.forEach((x) => x.dispose()); else m.dispose();
        }
      });
      // shared resources that may not be in the scene right now (no pins, no target)
      for (const r of [pinGeometry, pinRingGeometry, pinMaterial, pinRingMaterial, arcMaterial, targetMaterial, pulseMaterial]) {
        r.dispose();
      }
      landTexture.dispose();
      timer.dispose();
      renderer.dispose();
      renderer.forceContextLoss(); // frees the GPU context now; StrictMode mounts twice and browsers cap contexts
      canvas.remove();
    },
  };
}
