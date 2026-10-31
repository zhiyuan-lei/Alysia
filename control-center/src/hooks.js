import { useEffect, useState } from "react";
import { apiGet } from "./api";

export function useApi(path, deps = []) {
  const [state, setState] = useState({ data: null, loading: true, error: null });
  useEffect(() => {
    let active = true;
    setState({ data: null, loading: true, error: null });
    apiGet(path)
      .then((data) => active && setState({ data, loading: false, error: null }))
      .catch((error) => active && setState({ data: null, loading: false, error: error.message }));
    return () => { active = false; };
  }, [path, ...deps]);
  return state;
}
