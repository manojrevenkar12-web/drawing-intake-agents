import { useCallback, useEffect, useState } from "react";

export type Load<T> =
  | { state: "loading" }
  | { state: "error"; message: string; retry: () => void }
  | { state: "ready"; data: T };

const BASE = `${import.meta.env.BASE_URL}data/`;

export async function getJson<T>(name: string, fetcher: typeof fetch = fetch): Promise<T> {
  const res = await fetcher(`${BASE}${name}`);
  if (!res.ok) throw new Error(`${name} answered ${res.status}`);
  return (await res.json()) as T;
}

/** Load one JSON file from public/data, with a retry the error state can call. */
export function useJson<T>(name: string): Load<T> {
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<Load<T>>({ state: "loading" });
  const retry = useCallback(() => {
    setLoad({ state: "loading" });
    setAttempt((n) => n + 1);
  }, []);
  useEffect(() => {
    let live = true;
    getJson<T>(name)
      .then((data) => live && setLoad({ state: "ready", data }))
      .catch((err: Error) => live && setLoad({ state: "error", message: err.message, retry }));
    return () => {
      live = false;
    };
  }, [name, attempt, retry]);
  return load;
}
