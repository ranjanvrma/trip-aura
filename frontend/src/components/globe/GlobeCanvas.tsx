import { useEffect, useRef } from "react";
import * as THREE from "three";
import gsap from "gsap";
import type { LatLng } from "../../types";
import { prefersReducedMotion } from "../../lib/safeUrl";

const DEG = Math.PI / 180;

/** Position on a unit sphere for a latitude/longitude (three.js: y up, longitude 0 facing +z). */
function toVec(lat: number, lng: number, r = 1): THREE.Vector3 {
  const phi = (90 - lat) * DEG;
  const theta = (lng + 90) * DEG;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(theta), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(theta));
}

/** Decorative dotted globe that turns to show the chosen destination. Loaded lazily; see Globe.tsx. */
export default function GlobeCanvas({ target, onReady }: { target: LatLng | null; onReady: () => void }) {
  const host = useRef<HTMLDivElement>(null);
  const api = useRef<{ focus: (p: LatLng | null) => void } | null>(null);

  useEffect(() => {
    const el = host.current!;
    const reduced = prefersReducedMotion();
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, powerPreference: "low-power" });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    el.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 20);
    camera.position.set(0, 0, 4.2);

    const globe = new THREE.Group();
    globe.rotation.x = 0.35;
    scene.add(globe);

    // soft body
    const body = new THREE.Mesh(
      new THREE.SphereGeometry(0.985, 64, 48),
      new THREE.MeshBasicMaterial({ color: 0xf4efe6 }),
    );
    globe.add(body);

    // evenly spread dots (Fibonacci sphere)
    const N = 1600;
    const pos = new Float32Array(N * 3);
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2;
      const rad = Math.sqrt(1 - y * y);
      const th = i * Math.PI * (3 - Math.sqrt(5));
      pos.set([Math.cos(th) * rad, y, Math.sin(th) * rad], i * 3);
    }
    const dotsGeo = new THREE.BufferGeometry();
    dotsGeo.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    const dots = new THREE.Points(dotsGeo, new THREE.PointsMaterial({ color: 0x9fb4a3, size: 0.018, sizeAttenuation: true }));
    globe.add(dots);

    // latitude rings
    const ringMat = new THREE.LineBasicMaterial({ color: 0xd9cfbf, transparent: true, opacity: 0.9 });
    for (const lat of [-60, -30, 0, 30, 60]) {
      const pts = Array.from({ length: 129 }, (_, i) => toVec(lat, (i / 128) * 360 - 180, 1.002));
      globe.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), ringMat));
    }

    // destination marker
    const marker = new THREE.Group();
    const pin = new THREE.Mesh(new THREE.SphereGeometry(0.035, 16, 12), new THREE.MeshBasicMaterial({ color: 0xc98a5a }));
    const halo = new THREE.Mesh(new THREE.RingGeometry(0.05, 0.075, 40),
      new THREE.MeshBasicMaterial({ color: 0xc98a5a, transparent: true, opacity: 0.55, side: THREE.DoubleSide }));
    marker.add(pin, halo);
    marker.visible = false;
    globe.add(marker);

    const resize = () => {
      const { width, height } = el.getBoundingClientRect();
      renderer.setSize(width, height, false);
      camera.aspect = width / Math.max(height, 1);
      camera.updateProjectionMatrix();
    };
    resize();
    const ro = new ResizeObserver(resize);
    ro.observe(el);

    let spinning = !reduced;
    let visible = true;
    let frame = 0;
    const timer = new THREE.Timer();
    const tick = () => {
      frame = requestAnimationFrame(tick);
      timer.update();
      if (!visible || document.hidden) return;
      const dt = Math.min(timer.getDelta(), 0.1);
      if (spinning) globe.rotation.y += dt * 0.12;
      if (marker.visible) {
        const s = 1 + 0.35 * Math.sin(timer.getElapsed() * 2.2);
        halo.scale.setScalar(s);
        (halo.material as THREE.MeshBasicMaterial).opacity = 0.6 - 0.35 * (s - 1) / 0.35;
      }
      renderer.render(scene, camera);
    };
    tick();
    onReady();

    // render only while on screen
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; });
    io.observe(el);

    api.current = {
      focus: (p) => {
        if (!p) { marker.visible = false; spinning = !reduced; return; }
        spinning = false;
        const v = toVec(p.lat, p.lng, 1.0);
        marker.position.copy(v);
        marker.lookAt(v.clone().multiplyScalar(2));
        marker.visible = true;
        // shortest turn so the city faces the camera; gsap.to overwrites a running tween, so the turn is interruptible
        const wantY = -p.lng * DEG;   // rotation.y that brings this longitude to face +z (the camera)
        const curY = globe.rotation.y;
        const deltaY = ((wantY - curY + Math.PI) % (2 * Math.PI) + 2 * Math.PI) % (2 * Math.PI) - Math.PI;
        const props = { y: curY + deltaY, x: Math.max(-1, Math.min(1, p.lat * DEG)) };
        gsap.to(globe.rotation, { ...props, duration: reduced ? 0 : 1.4, ease: "power3.inOut", overwrite: true });
      },
    };

    return () => {
      cancelAnimationFrame(frame);
      ro.disconnect();
      io.disconnect();
      gsap.killTweensOf(globe.rotation);
      scene.traverse((o) => {
        const m = o as THREE.Mesh;
        m.geometry?.dispose?.();
        const mat = m.material as THREE.Material | THREE.Material[] | undefined;
        if (Array.isArray(mat)) mat.forEach((x) => x.dispose()); else mat?.dispose?.();
      });
      renderer.dispose();
      el.removeChild(renderer.domElement);
      api.current = null;
    };
  }, [onReady]);

  useEffect(() => { api.current?.focus(target); }, [target]);

  return <div ref={host} className="globe-canvas" aria-hidden />;
}
