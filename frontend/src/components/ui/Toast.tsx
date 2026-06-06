import { useEffect, useRef, useState } from "react";

export function Toast({
  message,
  onDone,
}: {
  message: string;
  onDone: () => void;
}) {
  const [visible, setVisible] = useState(false);
  const doneRef = useRef(onDone);

  useEffect(() => {
    doneRef.current = onDone;
  }, [onDone]);

  useEffect(() => {
    setVisible(false);

    const enterTimer = window.setTimeout(() => setVisible(true), 20);
    const leaveTimer = window.setTimeout(() => setVisible(false), 2600);
    const doneTimer = window.setTimeout(() => doneRef.current(), 3000);

    return () => {
      window.clearTimeout(enterTimer);
      window.clearTimeout(leaveTimer);
      window.clearTimeout(doneTimer);
    };
  }, [message]);

  return (
    <div className={["toast", visible ? "toast-visible" : ""].join(" ")} role="status">
      {message}
    </div>
  );
}
