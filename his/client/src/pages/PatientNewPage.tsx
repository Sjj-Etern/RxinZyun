import { useNavigate } from 'react-router-dom';
import { useEffect } from 'react';

// Redirect to patient list — new patient is created via modal
export default function PatientNewPage() {
  const navigate = useNavigate();
  useEffect(() => { navigate('/patients', { replace: true }); }, [navigate]);
  return null;
}
