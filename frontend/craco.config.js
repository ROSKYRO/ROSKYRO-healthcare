// CRACO wraps CRA's default webpack/babel/postcss config unmodified --
// this file exists mainly so the project matches the "React + CRACO"
// tooling target, and gives a single documented place to add webpack
// overrides later without ejecting. Tailwind/PostCSS keep working exactly
// as before: CRA's built-in postcss-loader already picks up
// postcss.config.js automatically, and CRACO doesn't change that pipeline
// unless you override `style.postcss` here.
module.exports = {
  style: {
    postcss: {
      mode: "extends",
    },
  },
};
