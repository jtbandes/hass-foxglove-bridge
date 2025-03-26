# Home Assistant Foxglove Bridge

This integration enables Home Assistant data to be visualized with [Foxglove](https://foxglove.dev). You can view a live dashboard, or record to a [MCAP file](https://mcap.dev).


## Setup

1. Ensure you have [installed the Home Assistant Community Store](https://hacs.xyz/docs/use/) integration (HACS).
1. Add this repository to HACS:

    [![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=jtbandes&repository=hass-foxglove-bridge&category=integration)

1. Set up the "Foxglove Bridge" integration:

    [![Open your Home Assistant instance and add a Foxglove Bridge integration.](https://my.home-assistant.io/badges/brand.svg)](https://my.home-assistant.io/redirect/config_flow_start/?domain=foxglove_bridge)


1. Follow the steps to add the integration. Leave the host and port settings at their default values unless you have a reason to use different settings.

    <img width="300" alt="Foxglove Bridge integration settings dialog" src="https://github.com/user-attachments/assets/1543c4fa-0f8c-497b-b30a-a1d42732d354" />


## Usage

### Live visualization

1. Once the integration is configured, [open Foxglove](https://app.foxglove.dev/) in Chrome, click "Open connection" and enter your Home Assistant URL followed by the port number configured when setting up the integration, usually 8765.
(See [Foxglove docs](https://docs.foxglove.dev/docs/connecting-to-data/introduction))

    For example, if your Home Assistant URL is `homeassistant.local`, you can visit: https://app.foxglove.dev/~/view?ds=foxglove-websocket&ds.url=ws://homeassistant.local:8765

    <img width="962" alt="Open Connection dialog in Foxglove" src="https://github.com/user-attachments/assets/0acecf51-41e3-4ef2-b6c1-0b59b9de905e" />

1. If you receive a security error, click the shield icon in the address bar and select "Load Unsafe Scripts". This error appears because the browser by default doesn't allow an `https` page to connect to servers that aren't using SSL.

1. Browse the list of available entities in the Topics sidebar on the left. You can view an entity's state by using a [panel](https://docs.foxglove.dev/docs/visualization/panels/introduction) (analogous to a Home Assistant [Card](https://www.home-assistant.io/dashboards/cards/)). Click the Add Panel button in the top bar, and try adding a [Raw Messages](https://docs.foxglove.dev/docs/visualization/panels/raw-messages) panel to view states and attributes for a single entity.

    <img width="250" alt="Adding a Raw Message panel" src="https://github.com/user-attachments/assets/179ccc33-c726-4166-b598-e5f9a1ce2ce0" />

    <img width="824" alt="Visualizing entity states in the Raw Message panel" src="https://github.com/user-attachments/assets/18c7eb2a-1ec2-4caf-9543-1e14dd7cc837" />

1. For numeric or discrete data, try using the [Plot](https://docs.foxglove.dev/docs/visualization/panels/plot) or [State Transitions](https://docs.foxglove.dev/docs/visualization/panels/state-transitions) panels for visualization:

    <img width="981" alt="Viewing data in Plot and State Transitions panels" src="https://github.com/user-attachments/assets/5f8d39a4-ebcb-4e5a-8083-e1c1ac5b064a" />


### Services

When using a live connection, you can use Foxglove's [Service Call panel](https://docs.foxglove.dev/docs/visualization/panels/service-call) to invoke Home Assistant [Actions](https://www.home-assistant.io/docs/scripts/perform-actions/) (a.k.a. Services).

In the [panel settings](https://docs.foxglove.dev/docs/visualization/panels/introduction#edit-settings), select from the available services. Enter your request parameters as JSON in the "Request" box and click the button to call the service.

<img width="810" alt="Call a service using the Service Call panel" src="https://github.com/user-attachments/assets/4fefaad9-8682-4f32-9aac-67911e0a250e" />


### MCAP recording

1. Visit the integration's service settings page and toggle the "MCAP Recording" switch on. This will start logging state changes to an [MCAP file](https://mcap.dev).

    <img width="756" alt="MCAP recording" src="https://github.com/user-attachments/assets/f5f2d64e-329d-4a8b-928d-5501867ff3d7" />

1. Turn the switch off again to stop recording.

1. The MCAP file will be saved to your media directory, for example `/media/foxglove_bridge/home_assistant_1743012122854908268.mcap`.


1. Once you have an MCAP file, you can inspect it using the [MCAP CLI](https://mcap.dev/guides/cli), [APIs](https://mcap.dev/reference), or by [viewing it in Foxglove](https://docs.foxglove.dev/docs/connecting-to-data/local-data).
