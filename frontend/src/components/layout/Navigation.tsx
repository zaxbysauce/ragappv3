import { NavigationRail } from "./NavigationRail";
import { MobileBottomNav } from "./MobileBottomNav";
import type { NavigationProps } from "./navigationTypes";

export function Navigation(props: NavigationProps) {
  return (
    <>
      {/* Desktop: Navigation Rail */}
      <div className="hidden md:flex">
        <NavigationRail healthStatus={props.healthStatus} />
      </div>

      {/* Mobile: Bottom Navigation */}
      <div className="flex md:hidden">
        <MobileBottomNav activeItem={props.activeItem} onItemSelect={props.onItemSelect} />
      </div>
    </>
  );
}
