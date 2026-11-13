// GLSL for the globe. Colours arrive as linear-space uniforms (THREE.Color converts from sRGB) and each fragment
// shader ends with three's colorspace chunk, so the output matches the hex values in scene.ts.

/** Shared by the globe and the halo: object position plus view-space normal and position. */
export const surfaceVertex = /* glsl */ `
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
void main() {
  vObj = position;
  vNormalV = normalize(normalMatrix * normal);
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  vPosV = mv.xyz;
  gl_Position = projectionMatrix * mv;
}
`;

export const globeFragment = /* glsl */ `
#define GLOBE_PI 3.141592653589793
uniform sampler2D uLand;
uniform vec2 uTexel;
uniform vec3 uSun;
uniform vec3 uNight;
uniform vec3 uOceanCentre;
uniform vec3 uOceanEdge;
uniform vec3 uShallow;
uniform vec3 uLandLight;
uniform vec3 uLandDeep;
uniform vec3 uCoast;
uniform vec3 uPolar;
uniform vec3 uAtmosphere;
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;

// Small 3D value noise sampled on the sphere itself, so the land tint has no seam at the antimeridian.
float hash(vec3 p) {
  p = fract(p * 0.3183099 + 0.1);
  p *= 17.0;
  return fract(p.x * p.y * p.z * (p.x + p.y + p.z));
}
float noise(vec3 x) {
  vec3 i = floor(x);
  vec3 f = fract(x);
  f = f * f * (3.0 - 2.0 * f);
  return mix(
    mix(mix(hash(i), hash(i + vec3(1, 0, 0)), f.x), mix(hash(i + vec3(0, 1, 0)), hash(i + vec3(1, 1, 0)), f.x), f.y),
    mix(mix(hash(i + vec3(0, 0, 1)), hash(i + vec3(1, 0, 1)), f.x), mix(hash(i + vec3(0, 1, 1)), hash(i + vec3(1, 1, 1)), f.x), f.y),
    f.z);
}

float landAt(vec2 uv) { return texture2D(uLand, uv).r; }

void main() {
  // Same latitude/longitude convention as geo.ts: theta = atan(z, -x) = lng + 90 deg.
  vec3 p = normalize(vObj);
  float lat = asin(clamp(p.y, -1.0, 1.0));
  float theta = atan(p.z, -p.x);
  vec2 uv = vec2(fract(theta / (2.0 * GLOBE_PI) + 0.25), 0.5 + lat / GLOBE_PI);

  float land = landAt(uv);
  vec2 o = uTexel * 2.0;
  float around = 0.25 * (landAt(uv + vec2(o.x, 0.0)) + landAt(uv - vec2(o.x, 0.0))
                       + landAt(uv + vec2(0.0, o.y)) + landAt(uv - vec2(0.0, o.y)));

  vec3 n = normalize(vNormalV);
  vec3 v = normalize(-vPosV);
  float facing = clamp(dot(n, v), 0.0, 1.0);
  float rim = 1.0 - facing;

  // Ocean: pale in the middle, deeper toward the limb, a lighter shelf along the coasts.
  vec3 ocean = mix(uOceanCentre, uOceanEdge, smoothstep(0.0, 1.0, pow(rim, 1.3)));
  ocean = mix(ocean, uShallow, (1.0 - land) * around * 0.85);

  // Land: two greens broken up by noise, paler toward the poles, a darker line at the coast.
  float k = noise(p * 5.0) * 0.65 + noise(p * 13.0) * 0.35;
  vec3 ground = mix(uLandLight, uLandDeep, smoothstep(0.3, 0.75, k));
  ground = mix(ground, uPolar, smoothstep(1.08, 1.26, abs(lat)));
  ground = mix(ground, uCoast, clamp(land * (1.0 - around) * 1.8, 0.0, 0.7));
  vec3 col = mix(ocean, ground, smoothstep(0.35, 0.65, land));

  // Daylight from the subsolar point: a soft terminator about 20 degrees wide; night is cooler and darker, never black.
  float day = smoothstep(-0.12, 0.22, dot(p, uSun));
  col *= mix(uNight, vec3(1.0), day);
  col *= 0.94 + 0.06 * facing;

  // A little sky colour at the limb, stronger on the lit side, so the sphere reads as round.
  col = mix(col, uAtmosphere, pow(rim, 3.0) * (0.3 + 0.35 * day));

  gl_FragColor = vec4(col, 1.0);
  #include <colorspace_fragment>
}
`;

/** Rendered on the back faces of a slightly larger sphere: strongest at the globe's edge, gone at its own. */
export const haloFragment = /* glsl */ `
uniform vec3 uColor;
uniform float uStrength;
varying vec3 vObj;
varying vec3 vNormalV;
varying vec3 vPosV;
void main() {
  float t = dot(normalize(vNormalV), normalize(vPosV));
  float a = pow(smoothstep(0.0, 0.5, t), 1.8) * uStrength;
  gl_FragColor = vec4(uColor, a);
  #include <colorspace_fragment>
}
`;

export const dotsVertex = /* glsl */ `
uniform float uSize;
uniform vec3 uSun;
varying float vFade;
varying float vDay;
void main() {
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  float facing = dot(normalize(normalMatrix * position), normalize(-mv.xyz));
  vFade = smoothstep(0.05, 0.45, facing);          // thin out toward the limb where dots crowd together
  vDay = smoothstep(-0.12, 0.22, dot(normalize(position), uSun));
  gl_PointSize = uSize * (0.55 + 0.45 * max(facing, 0.0));
  gl_Position = projectionMatrix * mv;
}
`;

export const dotsFragment = /* glsl */ `
uniform vec3 uColor;
uniform vec3 uNight;
uniform float uOpacity;
varying float vFade;
varying float vDay;
void main() {
  float d = length(gl_PointCoord - 0.5);
  float a = (1.0 - smoothstep(0.32, 0.5, d)) * vFade * uOpacity;
  if (a < 0.01) discard;
  gl_FragColor = vec4(uColor * mix(uNight, vec3(1.0), vDay), a);
  #include <colorspace_fragment>
}
`;
