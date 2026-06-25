using System;
using UnityEngine;

public static class SHMEvents
{
    // Data events
    public static Action<VibrationData[]> OnVibrationDataReceived;
    public static Action<CrackData[]> OnCrackDataReceived;
    public static Action<string> OnDataError;
    
    // UI Control events
    public static Action<bool> OnSilenceToggled;  // bool indicates if silenced
    public static Action OnAlertAcknowledged;
}