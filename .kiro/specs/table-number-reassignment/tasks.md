# Implementation Plan: Table Number Reassignment

## Overview

This implementation adds the ability for authorized staff (Cashier, Admin, Super Admin) to edit table numbers for pending dine-in orders through the admin dashboard. The implementation follows a simple inline-edit pattern with AJAX updates, focusing on core functionality without advanced features like bulk operations, audit trail, or kitchen display integration.

**Technology Stack:** Python (Flask), Jinja2 templates, JavaScript (jQuery), SQLAlchemy

**Key Implementation Points:**
- Backend: New Flask route for table number updates with validation
- Frontend: Inline edit controls in the orders list with AJAX submission
- Validation: Client-side and server-side validation for positive integers
- Authorization: Role-based access control (Cashier, Admin, Super Admin only)
- Status restriction: Only PENDING dine-in orders can be edited

## Tasks

- [x] 1. Implement backend route for table number updates
  - [x] 1.1 Create POST endpoint `/admin/orders/<int:order_id>/update-table` in `routes/admin/__init__.py`
    - Accept JSON request body with `table_number` field
    - Implement authorization check using `@login_required` and `@admin_required` decorators
    - Validate table_number is a positive integer
    - Fetch order by ID and validate it exists
    - Validate order is dine-in (`dining_option == 'DINE_IN'`)
    - Validate order status is PENDING (`status == 'PENDING'`)
    - Update `order.table_number` field and commit to database
    - Return JSON response with success status and message
    - Include error handling with database rollback on failure
    - _Requirements: 2.1, 2.5, 3.1, 3.3, 4.2, 5.1, 11.3_
  
  - [ ]* 1.2 Write unit tests for table number update endpoint
    - Test successful update for PENDING dine-in order
    - Test rejection of non-positive integers (0, -1, non-numeric)
    - Test rejection for non-PENDING orders (PREPARING, COMPLETED, CANCELLED)
    - Test rejection for non-dine-in orders (DELIVERY, TAKE_OUT)
    - Test 404 error for non-existent order ID
    - Test 400 error for missing table_number in request body
    - Test authorization: reject requests from users with role 'USER'
    - _Requirements: 2.5, 3.3, 4.1, 5.1, 5.2, 5.3, 11.3_

- [x] 2. Update admin orders list template to display table numbers
  - [x] 2.1 Modify `templates/admin/orders.html` to add table number column
    - Add new table header "Table #" in the orders table
    - Add table cell displaying table_number for each order
    - Display table_number value for dine-in orders
    - Display "N/A" for delivery and takeout orders (`dining_option != 'DINE_IN'`)
    - Add data attributes: `data-order-id`, `data-status`, `data-dining-option`
    - _Requirements: 1.1, 1.2, 11.2_
  
  - [x] 2.2 Add inline edit controls for PENDING dine-in orders
    - Add edit button (icon) next to table number for PENDING dine-in orders
    - Add hidden edit form with number input, save button, and cancel button
    - Set input attributes: `type="number"`, `min="1"`, `step="1"`
    - Show edit controls only when `status == 'PENDING'` and `dining_option == 'DINE_IN'`
    - Show read-only table number for completed orders
    - _Requirements: 2.1, 2.2, 3.2_

- [x] 3. Implement frontend JavaScript for inline editing
  - [x] 3.1 Add edit button click handler in `templates/admin/orders.html`
    - Hide table number display and edit button
    - Show edit form with input field
    - Set focus on input field
    - _Requirements: 2.2, 2.3_
  
  - [x] 3.2 Add cancel button click handler
    - Hide edit form
    - Show table number display and edit button
    - Reset input field to original value
    - _Requirements: 2.2_
  
  - [x] 3.3 Add save button click handler with client-side validation
    - Get order ID from data attribute
    - Get new table number from input field
    - Validate input is a positive integer (> 0)
    - Display error message if validation fails
    - Keep focus on input field if validation fails
    - Call AJAX function to submit update if validation passes
    - _Requirements: 2.3, 2.4, 5.1, 5.2, 5.3, 5.5_
  
  - [x] 3.4 Implement AJAX submission function
    - Send POST request to `/admin/orders/<order_id>/update-table`
    - Set content type to `application/json`
    - Send JSON body with `table_number` field
    - Handle success response: update displayed table number, hide edit form, show success message
    - Handle error response: display error message from server
    - Handle network errors: display generic error message
    - _Requirements: 2.5, 6.1, 6.2, 6.3_
  
  - [x] 3.5 Implement notification display functions
    - Create `showSuccess(message)` function: display success alert, auto-dismiss after 3 seconds
    - Create `showError(message)` function: display error alert, manual dismiss
    - Add notification container div to template if not present
    - Style notifications using Bootstrap alert classes
    - _Requirements: 6.1, 6.4, 6.5_

- [x] 4. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

- [x] 5. Verify orders route includes table_number field
  - [x] 5.1 Check `routes/admin/__init__.py` orders list route
    - Verify the orders query includes `table_number` field in results
    - Verify `table_number` is passed to template context
    - Add explicit field selection if needed (SQLAlchemy should include by default)
    - _Requirements: 1.1_

- [ ] 6. Add CSS styling for inline edit controls (if needed)
  - [ ] 6.1 Add styles for edit controls in `templates/admin/orders.html` or separate CSS file
    - Style edit button to be subtle (icon-only, small size)
    - Style edit form to be inline and compact
    - Style input field to match table cell width
    - Style save/cancel buttons to be small and inline
    - Ensure responsive design for mobile devices
    - Add hover effects for edit button
    - _Requirements: 2.2_

- [ ] 7. Final integration and testing
  - [ ]* 7.1 Write integration test for end-to-end flow
    - Create test PENDING dine-in order in database
    - Login as cashier user
    - Navigate to orders page
    - Verify table number column is displayed
    - Verify edit button appears for PENDING dine-in order
    - Click edit button and verify form appears
    - Enter new table number and click save
    - Verify AJAX request is sent with correct data
    - Verify table number is updated in database
    - Verify success message is displayed
    - Verify table number display is updated without page reload
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 6.1, 6.2_
  
  - [ ]* 7.2 Write integration test for read-only display
    - Create test orders with different statuses (PREPARING, COMPLETED, CANCELLED)
    - Create test orders with different dining options (DELIVERY, TAKE_OUT)
    - Verify edit button does NOT appear for completed orders
    - Verify "N/A" is displayed for non-dine-in orders
    - Verify read-only table number is displayed for completed dine-in orders
    - _Requirements: 1.2, 3.2, 11.2_
  
  - [ ]* 7.3 Manual testing checklist
    - Test in Chrome, Firefox, and Safari browsers
    - Test with different user roles (Cashier, Admin, Super Admin, regular User)
    - Test validation: enter 0, -1, non-numeric values
    - Test concurrent editing: open two browser windows and edit same order
    - Test status change during editing: change order status while edit form is open
    - Test network error handling: disconnect network and try to save
    - Test success message auto-dismiss after 3 seconds
    - Test error message manual dismiss
    - Verify responsive design on mobile screen sizes
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 3.1, 3.2, 3.3, 4.1, 5.1, 5.2, 5.3, 6.1, 6.2, 6.3, 6.4, 6.5_

- [ ] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- The implementation focuses on the simple approach outlined in the design document
- Advanced features (bulk operations, audit trail, kitchen display, mobile app) are explicitly excluded
- The existing `table_number` field in the Order model is used; no database migration is required
- Authorization is handled by existing Flask decorators (`@login_required`, `@admin_required`)
- The implementation uses jQuery for AJAX calls (assumed to be already included in admin templates)
- Bootstrap CSS classes are used for styling (assumed to be already included in admin templates)

## Out of Scope

The following requirements are NOT implemented in this phase:
- **Requirement 7:** Display table reassignment history (audit trail)
- **Requirement 8:** Optimistic locking for concurrent editing (using simple last-write-wins)
- **Requirement 9:** Support bulk table reassignment
- **Requirement 10:** Integrate with kitchen display
- **Requirement 12:** Mobile app read-only display with real-time updates

These features can be added in future iterations based on user feedback and operational needs.
