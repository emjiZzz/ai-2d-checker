module.exports = {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [
      2,
      "always",
      [
        "feat",
        "fix",
        "docs",
        "style",
        "refactor",
        "perf",
        "test",
        "build",
        "ci",
        "chore",
        "revert",
        "security"
      ]
    ],
    "subject-case": [2, "always", ["sentence-case", "start-case", "pascal-case", "upper-case", "kebab-case", "lower-case"]]
  }
};
