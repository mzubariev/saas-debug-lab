export const profiles = {
    baseline: {
      vus: 20,
      duration: '30m',
    },
    high_load: {
      vus: 100,
      duration: '10m',
    },
    spike: {
      stages: [
        { duration: '10s', target: 0 },
        { duration: '15s', target: 150 },
        { duration: '30s', target: 150 },
        { duration: '10s', target: 0 },
      ],
    },
  };