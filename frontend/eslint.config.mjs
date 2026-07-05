import next from "eslint-config-next";

// Next 16 ships a native flat-config array — no FlatCompat shim needed.
const eslintConfig = [
  ...next,
  {
    // Generated API types are never hand-edited, so never linted (§4d).
    ignores: ["lib/api-types.gen.ts", "out/**", ".next/**"],
  },
];

export default eslintConfig;
