import type { DashboardModuleKey } from '../data/dashboardModules';

export type ModuleIconName =
  | DashboardModuleKey
  | 'dashboard'
  | 'prescriptionNew'
  | 'review'
  | 'medicines'
  | 'scan'
  | 'pending'
  | 'medicineTotal'
  | 'patientTotal';

interface Props {
  name: ModuleIconName;
  size?: number;
}

export default function ModuleIcon({ name, size = 58 }: Props) {
  const accent = '#38BFC1';

  return (
    <svg className="module-picture" width={size} height={size} viewBox="0 0 64 64" aria-hidden="true">
      <rect x="6" y="5" width="52" height="54" rx="18" fill="#F8FDFF" />
      <path d="M12 13c8-5 27-5 39 8 5 6 6 17 1 25-5 9-16 12-28 10C11 54 6 46 8 34c1-9-2-16 4-21Z" fill="#DDF5FF" fillOpacity="0.86" />
      <path d="M38 8c11 5 17 15 16 25-1 8-6 15-13 18 11-7 12-23 0-31-7-5-17-6-28-2 7-8 16-13 25-10Z" fill="#FFF1F7" fillOpacity="0.74" />
      <rect x="7.5" y="6.5" width="49" height="51" rx="16.5" fill="none" stroke="white" strokeOpacity="0.86" strokeWidth="3" />
      {renderGlyph(name, accent)}
    </svg>
  );
}

function renderGlyph(name: Props['name'], accent: string) {
  const line = '#6BBDEB';
  const blue = '#63B3ED';

  switch (name) {
    case 'dispense':
      return (
        <>
          <path d="M39 17l8 8-21 21-8 2 2-8 21-21Z" fill={accent} />
          <path d="M36 20l8 8M25 38l5 5M41 17l6-6M49 13l4-4" stroke={line} strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'medicineInfo':
    case 'medicines':
    case 'medicineTotal':
      return (
        <>
          <rect x="16" y="28" width="32" height="15" rx="7.5" fill={accent} />
          <path d="M32 28v15" stroke="white" strokeWidth="3" strokeLinecap="round" />
          <circle cx="25" cy="23" r="7" fill="#78E1D7" />
          <circle cx="39" cy="23" r="7" fill={blue} fillOpacity="0.84" />
        </>
      );
    case 'reports':
      return (
        <>
          <path d="M18 44h28" stroke={line} strokeWidth="3" strokeLinecap="round" />
          <rect x="20" y="31" width="6" height="12" rx="3" fill="#83D8F4" />
          <rect x="29" y="24" width="6" height="19" rx="3" fill={accent} />
          <rect x="38" y="18" width="6" height="25" rx="3" fill={blue} />
        </>
      );
    case 'patients':
    case 'patientTotal':
      return (
        <>
          <circle cx="32" cy="25" r="8" fill="#F4C7B3" />
          <path d="M18 48c2.4-9.6 7.1-14 14-14s11.6 4.4 14 14H18Z" fill={accent} />
          <path d="M27 43h10M32 38v10" stroke="white" strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'medicineLocations':
      return (
        <>
          <rect x="17" y="18" width="30" height="30" rx="8" fill={accent} />
          <path d="M17 29h30M27 18v30M37 18v30" stroke="white" strokeOpacity="0.82" strokeWidth="2.5" />
          <circle cx="32" cy="38" r="3" fill="white" />
        </>
      );
    case 'medicineSettings':
      return (
        <>
          <circle cx="32" cy="32" r="12" fill={accent} />
          <circle cx="32" cy="32" r="4" fill="white" />
          <path d="M32 14v7M32 43v7M14 32h7M43 32h7M19 19l5 5M40 40l5 5M45 19l-5 5M24 40l-5 5" stroke={line} strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'writeoff':
      return (
        <>
          <rect x="19" y="16" width="26" height="34" rx="7" fill={accent} />
          <path d="M25 27h14M25 35h10M25 43h14" stroke="white" strokeWidth="3" strokeLinecap="round" />
          <path d="M40 19l5-5" stroke={line} strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'operationLog':
    case 'dashboard':
    case 'pending':
      return (
        <>
          <rect x="18" y="17" width="28" height="32" rx="8" fill={accent} />
          <rect x="25" y="13" width="14" height="8" rx="4" fill="#83D8F4" />
          <path d="M25 29h14M25 37h10" stroke="white" strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'medicineDown':
      return (
        <>
          <rect x="18" y="19" width="28" height="27" rx="8" fill={accent} />
          <path d="M32 18v20M24 31l8 8 8-8" stroke="white" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case 'restock':
      return (
        <>
          <rect x="16" y="30" width="32" height="14" rx="7" fill={accent} />
          <path d="M32 22v20M22 32h20" stroke="white" strokeWidth="4" strokeLinecap="round" />
        </>
      );
    case 'inventory':
      return (
        <>
          <circle cx="29" cy="29" r="11" fill={accent} />
          <path d="M37 37l9 9" stroke={line} strokeWidth="4" strokeLinecap="round" />
          <path d="M24 29h10M29 24v10" stroke="white" strokeWidth="3" strokeLinecap="round" />
        </>
      );
    case 'prescriptions':
    case 'prescriptionNew':
      return (
        <>
          <rect x="19" y="15" width="26" height="34" rx="7" fill={accent} />
          <path d="M26 26h12M26 34h12M26 42h8" stroke="white" strokeWidth="3" strokeLinecap="round" />
          <path d="M39 15v8h6" fill="white" fillOpacity="0.52" />
          {name === 'prescriptionNew' && <path d="M39 40l9-9 4 4-9 9-6 2 2-6Z" fill="#F4C7B3" />}
        </>
      );
    case 'review':
      return (
        <>
          <circle cx="29" cy="29" r="11" fill={accent} />
          <path d="M37 37l9 9" stroke={line} strokeWidth="4" strokeLinecap="round" />
          <path d="M24 29l4 4 8-9" stroke="white" strokeWidth="3.4" strokeLinecap="round" strokeLinejoin="round" />
        </>
      );
    case 'scan':
      return (
        <>
          <rect x="17" y="22" width="30" height="24" rx="8" fill={accent} />
          <path d="M24 22l3-5h10l3 5" stroke={line} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          <circle cx="32" cy="34" r="7" fill="white" fillOpacity="0.92" />
          <circle cx="32" cy="34" r="3.2" fill={blue} />
        </>
      );
    default:
      return null;
  }
}
