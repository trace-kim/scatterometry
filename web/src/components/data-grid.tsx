// AG Grid (Community) themed from the CSS design tokens.
import {
  ClientSideRowModelModule,
  ModuleRegistry,
  NumberEditorModule,
  RowSelectionModule,
  TextEditorModule,
  themeQuartz,
  ValidationModule,
} from "ag-grid-community";
import { AgGridReact, type AgGridReactProps } from "ag-grid-react";
import { type Ref, useMemo } from "react";
import { cn } from "@/lib/utils";
import { useDark } from "@/viz/theme";

// Only the features the tables use (AllCommunityModule is ~1.2 MB). In development the
// validation module names any missing module in the console.
ModuleRegistry.registerModules([
  ClientSideRowModelModule,
  TextEditorModule,
  NumberEditorModule,
  RowSelectionModule,
  ...(import.meta.env.DEV ? [ValidationModule] : []),
]);

export function useGridTheme() {
  const dark = useDark();
  return useMemo(
    () =>
      themeQuartz.withParams({
        browserColorScheme: dark ? "dark" : "light",
        fontFamily: "inherit",
        fontSize: 12,
        headerFontSize: 11,
        headerFontWeight: 500,
        rowHeight: 28,
        headerHeight: 28,
        spacing: 4,
        wrapperBorderRadius: 6,
        backgroundColor: "var(--card)",
        foregroundColor: "var(--foreground)",
        headerBackgroundColor: "var(--muted)",
        headerTextColor: "var(--muted-foreground)",
        borderColor: "var(--border)",
        accentColor: "var(--primary)",
        inputFocusBorder: { color: "var(--ring)" },
        selectedRowBackgroundColor: dark ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.05)",
      }),
    [dark],
  );
}

export function DataGrid<T>({
  className,
  gridRef,
  ...props
}: AgGridReactProps<T> & { className?: string; gridRef?: Ref<AgGridReact<T>> }) {
  const theme = useGridTheme();
  return (
    <div className={cn("w-full", className)}>
      <AgGridReact<T> ref={gridRef} theme={theme} suppressMovableColumns stopEditingWhenCellsLoseFocus {...props} />
    </div>
  );
}
