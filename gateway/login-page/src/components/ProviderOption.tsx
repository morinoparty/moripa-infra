import type { ReactNode } from "react";
import { css } from "styled-system/css";
import { Button, type ButtonProps } from "../chlorophyll";

interface ProviderOptionProps {
  href: string;
  icon: ReactNode;
  label: string;
  /** この方法でログインできる人の条件 */
  requirement: string;
  intent: ButtonProps["intent"];
}

/** ログイン方法を 1 つ選ぶボタンと、その利用条件 */
export const ProviderOption = ({ href, icon, label, requirement, intent }: ProviderOptionProps) => (
  <div className={css({ display: "flex", flexDirection: "column", gap: "2" })}>
    {/* 遷移先は oauth2-proxy なので、button ではなく a として描画する */}
    <Button asChild intent={intent} size="lg" className={css({ width: "full", height: "12", textStyle: "md" })}>
      <a href={href}>
        {icon}
        {label}
      </a>
    </Button>
    <p className={css({ textStyle: "sm", color: "fg.muted", textAlign: "center" })}>{requirement}</p>
  </div>
);
