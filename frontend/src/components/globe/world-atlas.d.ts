// The project does not enable resolveJsonModule; these declarations type the two Natural Earth files the globe
// imports lazily.
declare module "world-atlas/land-50m.json" {
  const topology: import("topojson-specification").Topology;
  export default topology;
}

declare module "world-atlas/land-110m.json" {
  const topology: import("topojson-specification").Topology;
  export default topology;
}
