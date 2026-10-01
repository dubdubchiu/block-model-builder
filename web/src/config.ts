/** Title block values. Owner is set here; everything else comes from the build. */
export const APP = {
  name: "Block model builder",
  rev: "0.4",
  status: "Prototype",
  owner: "Walter Chiu",
  data: "Sample" as string,
} as const;

export const BUILD = { hash: __BUILD_HASH__, date: __BUILD_DATE__ } as const;
