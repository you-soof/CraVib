using UnityEngine;
using UnityEngine.EventSystems;

public class RotateScene : MonoBehaviour
{
    public float rotationSpeed = 100f;
    private Vector2 lastPosition;
    private bool isDragging = false;

    void Update()
    {
#if UNITY_EDITOR || UNITY_STANDALONE
        // Mouse input
        if (Input.GetMouseButtonDown(0))
        {
            if (EventSystem.current != null && EventSystem.current.IsPointerOverGameObject())
                return;

            lastPosition = Input.mousePosition;
            isDragging = true;
        }

        if (Input.GetMouseButton(0) && isDragging)
        {
            RotateSceneWithDelta((Vector2)Input.mousePosition - lastPosition);
            lastPosition = Input.mousePosition;
        }

        if (Input.GetMouseButtonUp(0))
        {
            isDragging = false;
        }

#elif UNITY_IOS || UNITY_ANDROID
        // Touch input
        if (Input.touchCount == 1)
        {
            Touch touch = Input.GetTouch(0);

            if (touch.phase == TouchPhase.Began)
            {
                if (EventSystem.current != null && EventSystem.current.IsPointerOverGameObject(touch.fingerId))
                    return;

                lastPosition = touch.position;
                isDragging = true;
            }

            if (touch.phase == TouchPhase.Moved && isDragging)
            {
                RotateSceneWithDelta(touch.position - lastPosition);
                lastPosition = touch.position;
            }

            if (touch.phase == TouchPhase.Ended || touch.phase == TouchPhase.Canceled)
            {
                isDragging = false;
            }
        }
#endif
    }

    private void RotateSceneWithDelta(Vector2 delta)
    {
        float rotY = -delta.x * rotationSpeed * Time.deltaTime;
        float rotX = delta.y * rotationSpeed * Time.deltaTime;

        transform.Rotate(Vector3.up, rotY, Space.World);
        transform.Rotate(Vector3.right, rotX, Space.Self);
    }
}