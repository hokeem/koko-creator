(() => {
  const priority = {
    friends: [
      "777fe577d4fb324a679a0b45dea857a5",
      "ec0ec7df47c84ffca94093a9064d6c26",
      "ce3d6c56758d42128513558f7658dac8",
    ],
    couple: [
      "dcfaaf6d1374a308bd140bb510675f07",
      "626de48b62a88e155ec86f7cb5b26d0f",
      "6ab786cb3ed845a3a0ae476e042913e2",
      "4582066d304ffa39062159448bce4859",
    ],
  };
  const originalPreferenceFirstCandidates = preferenceFirstCandidates;
  preferenceFirstCandidates = function (limit = Infinity) {
    const candidates = originalPreferenceFirstCandidates(Infinity);
    const ids = priority[answers.people] || [];
    if (!ids.length) return candidates.slice(0, limit);
    const byId = new Map(candidates.map(entry => [entry.entry_id, entry]));
    const pinned = ids.map(id => byId.get(id)).filter(Boolean);
    const seen = new Set(pinned.map(entry => entry.entry_id));
    return [...pinned, ...candidates.filter(entry => !seen.has(entry.entry_id))].slice(0, limit);
  };

  if (sessionStorage.getItem("koko_intro_reco_cache_version") !== "2") {
    for (let index = sessionStorage.length - 1; index >= 0; index--) {
      const key = sessionStorage.key(index);
      if (key && key.startsWith("koko_reco_cache_v4_paged_")) sessionStorage.removeItem(key);
    }
    sessionStorage.setItem("koko_intro_reco_cache_version", "2");
  }
})();
