// The project does not enable resolveJsonModule; these declarations type the two Natural Earth files the globe
// imports lazily (country shapes, which also carry the merged land).
declare module "world-atlas/countries-50m.json" {
  const topology: import("topojson-specification").Topology;
  export default topology;
}

declare module "world-atlas/countries-110m.json" {
  const topology: import("topojson-specification").Topology;
  export default topology;
}
