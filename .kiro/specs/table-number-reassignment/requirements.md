# Requirements Document

## Introduction

This feature enables staff members (Cashier, Admin, Super Admin) to reassign table numbers for pending dine-in orders through the admin dashboard. Currently, when customers place orders through the mobile app while seated at a specific table, the table number is fixed and cannot be changed. However, customers frequently move to different tables (e.g., to accommodate larger groups, better seating preferences, or table availability changes), creating a mismatch between the order's recorded table number and the customer's actual location. This feature allows authorized staff to update the table number on pending orders, ensuring accurate order delivery and improved customer service.

This addresses the security concern raised in panel review: "You are keeping or storing database that are critical and could not be exposed to editing for security." The table number is non-critical operational data that is safe to edit while orders are in pending status. Once orders are completed, the table number becomes historical data and will be locked from editing.

## Glossary

- **Admin_Dashboard**: The web interface used by staff to manage restaurant operations, accessible at `/admin` and related routes
- **Cashier_Portal**: The staff interface at `/cashier` for order processing and management
- **Order**: A customer's food order with status tracking, stored in the Order model
- **Table_Number**: The `table_number` field in the Order model indicating which table the customer is seated at
- **Pending_Order**: An Order with status equal to 'PENDING' (not yet completed or cancelled)
- **Completed_Order**: An Order with status equal to 'COMPLETED', 'CANCELLED', or 'PREPARING'
- **Dine_In_Order**: An Order with `dining_option` equal to 'DINE_IN'
- **Authorized_Staff**: Users with role 'CASHIER', 'ADMIN', or 'SUPER_ADMIN'
- **Table_Reassignment_System**: The system component that handles table number updates
- **Order_Status**: The `status` field in the Order model with values: PENDING, PREPARING, COMPLETED, CANCELLED
- **Customer**: A user with role 'USER' who places orders through the mobile app

## Requirements

### Requirement 1: Display Table Number for Dine-In Orders

**User Story:** As a cashier, I want to see the table number for each dine-in order in the order list, so that I can identify which orders may need table reassignment.

#### Acceptance Criteria

1. WHEN an Authorized_Staff member views the order list in the Admin_Dashboard, THE Admin_Dashboard SHALL display the Table_Number for each Dine_In_Order
2. THE Admin_Dashboard SHALL display a placeholder or "N/A" for orders where `dining_option` is not 'DINE_IN'
3. THE Admin_Dashboard SHALL visually distinguish Dine_In_Orders from other order types
4. FOR EACH Dine_In_Order, THE Admin_Dashboard SHALL display the current Order_Status alongside the Table_Number

### Requirement 2: Enable Table Number Editing for Pending Orders

**User Story:** As a cashier, I want to edit the table number for pending dine-in orders, so that I can correct the table assignment when customers move to different tables.

#### Acceptance Criteria

1. WHEN an Authorized_Staff member views a Pending_Order with `dining_option` equal to 'DINE_IN', THE Admin_Dashboard SHALL display an edit control for the Table_Number field
2. THE Admin_Dashboard SHALL provide an inline edit interface (button, icon, or direct input field) to modify the Table_Number
3. WHEN the Authorized_Staff member clicks the edit control, THE Admin_Dashboard SHALL display an input field accepting integer values
4. THE Admin_Dashboard SHALL validate that the entered Table_Number is a positive integer
5. WHEN the Authorized_Staff member submits the new Table_Number, THE Table_Reassignment_System SHALL update the Order's `table_number` field in the database

### Requirement 3: Restrict Editing to Pending Orders Only

**User Story:** As a system administrator, I want table numbers to be editable only for pending orders, so that historical data for completed orders remains unchanged and auditable.

#### Acceptance Criteria

1. WHEN an Order has `status` equal to 'PREPARING', 'COMPLETED', or 'CANCELLED', THE Admin_Dashboard SHALL display the Table_Number as read-only text
2. THE Admin_Dashboard SHALL NOT display edit controls for Completed_Orders
3. WHEN an Authorized_Staff member attempts to edit a Completed_Order's Table_Number via direct API call, THE Table_Reassignment_System SHALL reject the request with an error message
4. THE Table_Reassignment_System SHALL return an error code indicating "Order status does not allow editing"

### Requirement 4: Enforce Role-Based Access Control

**User Story:** As a system administrator, I want only authorized staff to edit table numbers, so that customers cannot manipulate order data through the mobile app.

#### Acceptance Criteria

1. WHEN a user with role 'USER' attempts to access the table reassignment interface, THE Admin_Dashboard SHALL deny access
2. WHEN a user with role 'CASHIER', 'ADMIN', or 'SUPER_ADMIN' accesses the table reassignment interface, THE Admin_Dashboard SHALL grant access
3. WHEN an unauthorized user attempts to update a Table_Number via direct API call, THE Table_Reassignment_System SHALL reject the request with HTTP 403 Forbidden
4. THE Table_Reassignment_System SHALL log all table reassignment attempts with user_id and timestamp

### Requirement 5: Validate Table Number Input

**User Story:** As a cashier, I want the system to validate table numbers before saving, so that I don't accidentally enter invalid values.

#### Acceptance Criteria

1. WHEN an Authorized_Staff member enters a Table_Number, THE Admin_Dashboard SHALL validate that the value is a positive integer
2. WHEN the entered Table_Number is less than 1, THE Admin_Dashboard SHALL display an error message "Table number must be a positive integer"
3. WHEN the entered Table_Number is not a number, THE Admin_Dashboard SHALL display an error message "Please enter a valid table number"
4. THE Admin_Dashboard SHALL prevent submission of invalid Table_Number values
5. WHEN validation fails, THE Admin_Dashboard SHALL keep the input field focused for correction

### Requirement 6: Provide Confirmation Feedback

**User Story:** As a cashier, I want to receive confirmation when a table number is successfully updated, so that I know the change was saved.

#### Acceptance Criteria

1. WHEN a Table_Number is successfully updated, THE Admin_Dashboard SHALL display a success message "Table number updated to [new_number]"
2. THE Admin_Dashboard SHALL update the displayed Table_Number in the order list without requiring a page refresh
3. WHEN the update fails due to a server error, THE Admin_Dashboard SHALL display an error message with the failure reason
4. THE Admin_Dashboard SHALL automatically dismiss success messages after 3 seconds
5. THE Admin_Dashboard SHALL keep error messages visible until the user dismisses them

### Requirement 7: Display Table Reassignment History

**User Story:** As a manager, I want to see when and by whom table numbers were changed, so that I can audit order modifications and resolve customer disputes.

#### Acceptance Criteria

1. WHEN a Table_Number is updated, THE Table_Reassignment_System SHALL record the change with the previous value, new value, timestamp, and staff user_id
2. THE Admin_Dashboard SHALL provide a view to display table reassignment history for each Order
3. FOR EACH table reassignment record, THE Admin_Dashboard SHALL display the staff member's name, old table number, new table number, and timestamp
4. THE Admin_Dashboard SHALL sort table reassignment history by timestamp in descending order (most recent first)

### Requirement 8: Handle Concurrent Editing

**User Story:** As a system administrator, I want the system to handle cases where multiple staff members try to edit the same order simultaneously, so that data integrity is maintained.

#### Acceptance Criteria

1. WHEN two Authorized_Staff members attempt to update the same Order's Table_Number simultaneously, THE Table_Reassignment_System SHALL process updates sequentially
2. WHEN an Order's status changes from 'PENDING' to another status during editing, THE Table_Reassignment_System SHALL reject the table number update
3. THE Table_Reassignment_System SHALL return an error message "Order status has changed, table number cannot be updated"
4. WHEN a table number update is rejected due to status change, THE Admin_Dashboard SHALL refresh the order details to show the current status

### Requirement 9: Support Bulk Table Reassignment

**User Story:** As a cashier, I want to reassign multiple orders to a new table at once, so that I can efficiently handle situations where a group splits or merges tables.

#### Acceptance Criteria

1. THE Admin_Dashboard SHALL provide checkboxes to select multiple Pending_Orders with the same current Table_Number
2. THE Admin_Dashboard SHALL provide a bulk edit button that appears when multiple orders are selected
3. WHEN the bulk edit button is clicked, THE Admin_Dashboard SHALL display a dialog to enter the new Table_Number
4. WHEN the new Table_Number is submitted, THE Table_Reassignment_System SHALL update all selected orders
5. THE Admin_Dashboard SHALL display a summary showing how many orders were successfully updated and any failures

### Requirement 10: Integrate with Kitchen Display

**User Story:** As a kitchen staff member, I want to see updated table numbers on the kitchen display, so that I deliver food to the correct table.

#### Acceptance Criteria

1. WHEN a Table_Number is updated, THE Table_Reassignment_System SHALL emit a real-time notification to the kitchen display system
2. THE kitchen display SHALL update the Table_Number for the affected Order without requiring manual refresh
3. WHEN the kitchen display receives a table reassignment notification, THE kitchen display SHALL highlight the updated order for 5 seconds
4. THE kitchen display SHALL display both the old and new Table_Number in the notification for clarity

### Requirement 11: Restrict Editing for Delivery and Takeout Orders

**User Story:** As a system administrator, I want table number editing to be disabled for delivery and takeout orders, so that staff don't accidentally modify irrelevant fields.

#### Acceptance Criteria

1. WHEN an Order has `dining_option` equal to 'DELIVERY' or 'TAKE_OUT', THE Admin_Dashboard SHALL NOT display the Table_Number edit control
2. THE Admin_Dashboard SHALL display "N/A" or hide the Table_Number field for non-dine-in orders
3. WHEN an Authorized_Staff member attempts to update Table_Number for a non-dine-in order via API, THE Table_Reassignment_System SHALL reject the request
4. THE Table_Reassignment_System SHALL return an error message "Table number can only be updated for dine-in orders"

### Requirement 12: Mobile App Read-Only Display

**User Story:** As a customer, I want to see my current table number in the mobile app, so that I can verify my order details, but I should not be able to edit it.

#### Acceptance Criteria

1. WHEN a Customer views their Dine_In_Order in the mobile app, THE mobile app SHALL display the current Table_Number as read-only text
2. THE mobile app SHALL NOT provide any edit controls for the Table_Number field
3. WHEN the Table_Number is updated by staff, THE mobile app SHALL receive a real-time update and display the new Table_Number
4. THE mobile app SHALL display a notification "Your table number has been updated to [new_number]" when a change occurs
