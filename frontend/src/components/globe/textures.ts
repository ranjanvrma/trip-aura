// The Earth's imagery, loaded with the globe's own chunk. All four are equirectangular (longitude -180 at the left
// edge, north at the top) and come from NASA, which publishes them in the public domain:
// - day: Blue Marble (land, sea floor shading, ice);
// - night: Black Marble (city lights);
// - water: a land/water mask, used for the sun's glint on the sea;
// - clouds: a cloud composite. It is a typical sky, not today's weather.

import * as THREE from "three";
import cloudsUrl from "./textures/earth-clouds.jpg";
import dayUrl from "./textures/earth-day.jpg";
import nightUrl from "./textures/earth-night.jpg";
import waterUrl from "./textures/earth-water.jpg";

export interface EarthTextures {
  day: THREE.Texture;
  night: THREE.Texture;
  water: THREE.Texture;
  clouds: THREE.Texture;
}

function prepare(t: THREE.Texture, colour: boolean): THREE.Texture {
  t.colorSpace = colour ? THREE.SRGBColorSpace : THREE.NoColorSpace;
  t.wrapS = THREE.RepeatWrapping;      // longitude wraps, so the seam at the date line filters cleanly
  t.anisotropy = 8;                    // keeps coasts sharp where the surface turns away near the limb
  return t;
}

/** Plain colours for when the imagery cannot be loaded: the globe still draws, as a blue ball. */
function flat(r: number, g: number, b: number, colour: boolean): THREE.Texture {
  const t = new THREE.DataTexture(new Uint8Array([r, g, b, 255]), 1, 1);
  t.needsUpdate = true;
  return prepare(t, colour);
}

export function fallbackEarth(): EarthTextures {
  return { day: flat(22, 62, 110, true), night: flat(4, 8, 16, true), water: flat(255, 255, 255, false), clouds: flat(0, 0, 0, false) };
}

export async function loadEarth(): Promise<EarthTextures> {
  const loader = new THREE.TextureLoader();
  const [day, night, water, clouds] = await Promise.all([dayUrl, nightUrl, waterUrl, cloudsUrl].map((u) => loader.loadAsync(u)));
  return { day: prepare(day, true), night: prepare(night, true), water: prepare(water, false), clouds: prepare(clouds, false) };
}
