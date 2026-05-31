# Bugfix Requirements Document

## Introduction

This bugfix addresses a critical operational issue in the table management system where cashiers cannot release tables after customers finish eating. Currently, when a dine-in order is marked as READY and PAID, the table remains in OCCUPIED status indefinitely because there is no UI button in the Cashier Dashboard to trigger the existing backend endpoint `/orders/<order_id>/release-table`. This causes tables to remain unavailable for new customers, blocking restaurant operations and reducing seating capacity.

The backend functionality to release tables already exists and works correctly. The bug is specifically the missing UI control that prevents cashiers from accessing this functionality through the Cashier Dashboard interface.

**Impact:** Cashiers must manually update the database or restart the system to free up tables, causing operational delays and poor customer experience.

## Bug Analysis

### Current Behavior (Defect)

1.1 WHEN a dine-in order has status READY and payment_status PAID and the customer finishes eating THEN the cashier has no UI button to release the table in the Cashier Dashboard

1.2 WHEN a table is occupied by a completed order THEN the table_status remains 'OCCUPIED' indefinitely preventing new customers from being seated at that table

1.3 WHEN a cashier views the Cashier Dashboard order list THEN only the table reassignment button is visible but no table release button is available for READY/PAID orders

1.4 WHEN multiple customers finish eating at different tables THEN the cashier cannot batch-release multiple tables because no release functionality is exposed in the UI

### Expected Behavior (Correct)

2.1 WHEN a dine-in order has status READY and payment_status PAID THEN the Cashier Dashboard SHALL display a "Release Table" button next to the table number

2.2 WHEN the cashier clicks the "Release Table" button THEN the system SHALL call the existing `/orders/<order_id>/release-table` endpoint and set table_status to 'AVAILABLE'

2.3 WHEN a table is successfully released THEN the Cashier Dashboard SHALL display a success notification showing "Table [number] is now available" and update the UI without page refresh

2.4 WHEN the release operation fails THEN the Cashier Dashboard SHALL display an error message with the failure reason and keep the table status unchanged

2.5 WHEN a dine-in order has status READY and payment_status PAID THEN the "Release Table" button SHALL be visually distinct (e.g., green color, unlock icon) to indicate it frees up the table

### Unchanged Behavior (Regression Prevention)

3.1 WHEN a dine-in order has status PENDING or PREPARING THEN the system SHALL CONTINUE TO display only the table reassignment functionality without a release button

3.2 WHEN a table is released via the backend endpoint `/orders/<order_id>/release-table` THEN the system SHALL CONTINUE TO set table_status to 'AVAILABLE' and return the success response as currently implemented

3.3 WHEN an order has dining_option TAKE_OUT or DELIVERY THEN the system SHALL CONTINUE TO display "N/A" for the table number column without any table management buttons

3.4 WHEN the cashier edits a table number for a PENDING order THEN the existing table reassignment functionality SHALL CONTINUE TO work as currently implemented

3.5 WHEN the Cashier Dashboard polls for updates THEN the system SHALL CONTINUE TO refresh the order list and table statuses automatically as currently implemented

3.6 WHEN a non-authorized user attempts to access the release-table endpoint THEN the system SHALL CONTINUE TO enforce role-based access control and return HTTP 403 Forbidden
