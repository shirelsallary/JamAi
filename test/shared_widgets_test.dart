// Stage B — standalone tests for the new shared Dusk component library
// (lib/core/widgets/). These components aren't wired into any production
// screen yet, so each test pumps the widget directly (or inside a minimal
// MaterialApp/Scaffold for InkWell/Material ancestor requirements) rather
// than going through a real screen.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:jam_ai_app/core/theme.dart';
import 'package:jam_ai_app/core/widgets/widgets.dart';

Widget _host(Widget child) {
  return MaterialApp(
    theme: jamAiTheme,
    home: Scaffold(body: Center(child: child)),
  );
}

void main() {
  group('PrimaryButton', () {
    testWidgets('renders label and fires onPressed on tap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        PrimaryButton(label: 'Log in', onPressed: () => tapped = true),
      ));

      expect(find.text('Log in'), findsOneWidget);
      await tester.tap(find.byType(PrimaryButton));
      expect(tapped, isTrue);
    });

    testWidgets('null onPressed disables tap (no crash, callback never fires)', (tester) async {
      await tester.pumpWidget(_host(
        const PrimaryButton(label: 'Log in', onPressed: null),
      ));

      await tester.tap(find.byType(PrimaryButton));
      await tester.pump();
      // Nothing to assert beyond "didn't throw" — there's no callback to
      // observe when onPressed is null; disabled hit-testing is implicit.
      expect(find.text('Log in'), findsOneWidget);
    });

    testWidgets('isLoading shows a spinner instead of the label and blocks taps', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        PrimaryButton(label: 'Log in', onPressed: () => tapped = true, isLoading: true),
      ));

      expect(find.text('Log in'), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);

      await tester.tap(find.byType(PrimaryButton));
      expect(tapped, isFalse);
    });
  });

  group('SecondaryButton', () {
    testWidgets('renders label and fires onPressed on tap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        SecondaryButton(label: 'Share link', onPressed: () => tapped = true),
      ));

      expect(find.text('Share link'), findsOneWidget);
      await tester.tap(find.byType(SecondaryButton));
      expect(tapped, isTrue);
    });

    testWidgets('isLoading blocks taps', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        SecondaryButton(label: 'Share link', onPressed: () => tapped = true, isLoading: true),
      ));

      await tester.tap(find.byType(SecondaryButton));
      expect(tapped, isFalse);
    });
  });

  group('AppTextField', () {
    testWidgets('renders label/hint and reports changes', (tester) async {
      String? changed;
      await tester.pumpWidget(_host(
        AppTextField(labelText: 'Email', onChanged: (v) => changed = v),
      ));

      expect(find.text('Email'), findsOneWidget);
      await tester.enterText(find.byType(TextField), 'a@b.com');
      expect(changed, 'a@b.com');
    });

    testWidgets('enableSuggestions/autocorrect override the obscureText-linked default',
        (tester) async {
      await tester.pumpWidget(_host(
        const AppTextField(
          labelText: 'Email',
          enableSuggestions: false,
          autocorrect: false,
        ),
      ));

      final textField = tester.widget<TextField>(find.byType(TextField));
      // obscureText defaults to false, which would normally default both of
      // these to true — the explicit override must win.
      expect(textField.enableSuggestions, isFalse);
      expect(textField.autocorrect, isFalse);
    });

    testWidgets('.code preset matches JoinSessionScreen\'s current inline styling', (tester) async {
      String? changed;
      await tester.pumpWidget(_host(
        AppTextField.code(onChanged: (v) => changed = v),
      ));

      final textField = tester.widget<TextField>(find.byType(TextField));
      expect(textField.maxLength, 6);
      expect(textField.textAlign, TextAlign.center);
      expect(textField.textCapitalization, TextCapitalization.characters);
      expect(textField.style?.fontSize, 28);
      expect(textField.style?.fontWeight, FontWeight.bold);
      expect(textField.style?.letterSpacing, 8);
      expect(textField.decoration?.hintText, 'XXXXXX');

      await tester.enterText(find.byType(TextField), 'K7QX');
      expect(changed, 'K7QX');
    });
  });

  group('PlatformBadge', () {
    testWidgets('spotify variant shows the default label', (tester) async {
      await tester.pumpWidget(_host(
        const PlatformBadge(platform: AppPlatform.spotify),
      ));
      expect(find.text('Spotify'), findsOneWidget);
    });

    testWidgets('youtube variant with an explicit label override', (tester) async {
      await tester.pumpWidget(_host(
        const PlatformBadge(platform: AppPlatform.youtube, label: 'Joining via YouTube Music'),
      ));
      expect(find.text('Joining via YouTube Music'), findsOneWidget);
      expect(find.text('YouTube Music'), findsNothing);
    });
  });

  group('NoPlatformConnectedBanner', () {
    testWidgets('fires onConnect when the connect link is tapped', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        NoPlatformConnectedBanner(onConnect: () => tapped = true),
      ));

      await tester.tap(find.text('Connect Spotify or YouTube Music'));
      expect(tapped, isTrue);
    });
  });

  group('AppBanner', () {
    testWidgets('error variant renders the message and an action button that fires onAction',
        (tester) async {
      var retried = false;
      await tester.pumpWidget(_host(
        AppBanner(
          message: 'Could not connect',
          variant: AppBannerVariant.error,
          actionLabel: 'Retry',
          onAction: () => retried = true,
        ),
      ));

      expect(find.text('Could not connect'), findsOneWidget);
      expect(find.byIcon(Icons.error_outline), findsOneWidget);
      await tester.tap(find.text('Retry'));
      expect(retried, isTrue);
    });

    testWidgets('info variant uses the info icon and defaults when variant is omitted',
        (tester) async {
      await tester.pumpWidget(_host(
        const AppBanner(message: 'Queue is still building'),
      ));

      expect(find.text('Queue is still building'), findsOneWidget);
      expect(find.byIcon(Icons.info_outline), findsOneWidget);
    });

    testWidgets('isActionLoading swaps the action button for a spinner', (tester) async {
      await tester.pumpWidget(_host(
        const AppBanner(
          message: 'Could not connect',
          variant: AppBannerVariant.error,
          actionLabel: 'Retry',
          isActionLoading: true,
        ),
      ));

      expect(find.text('Retry'), findsNothing);
      expect(find.byType(CircularProgressIndicator), findsOneWidget);
    });

    testWidgets('actionKey is applied to the action button so call sites can find it directly',
        (tester) async {
      await tester.pumpWidget(_host(
        AppBanner(
          message: 'Could not connect with the Spotify app.',
          variant: AppBannerVariant.error,
          actionLabel: 'Use browser instead',
          actionKey: const Key('use-browser-instead-button'),
          onAction: () {},
        ),
      ));

      expect(find.byKey(const Key('use-browser-instead-button')), findsOneWidget);
    });

    testWidgets('with no actionLabel, renders message only', (tester) async {
      await tester.pumpWidget(_host(
        const AppBanner(message: 'Something went wrong', variant: AppBannerVariant.error),
      ));
      expect(find.text('Something went wrong'), findsOneWidget);
      expect(find.byType(TextButton), findsNothing);
    });
  });

  group('GradientBackground', () {
    testWidgets('renders its child on top of the glow layers', (tester) async {
      await tester.pumpWidget(_host(
        const GradientBackground(child: Text('content')),
      ));
      expect(find.text('content'), findsOneWidget);
    });
  });

  group('Avatar', () {
    testWidgets('shows initials when provided', (tester) async {
      await tester.pumpWidget(_host(const Avatar(initials: 'MJ')));
      expect(find.text('MJ'), findsOneWidget);
    });

    testWidgets('falls back to a person icon with no initials', (tester) async {
      await tester.pumpWidget(_host(const Avatar()));
      expect(find.byIcon(Icons.person), findsOneWidget);
    });
  });

  group('AppBackButton', () {
    testWidgets('fires onPressed on tap', (tester) async {
      var tapped = false;
      await tester.pumpWidget(_host(
        AppBackButton(onPressed: () => tapped = true),
      ));

      await tester.tap(find.byType(AppBackButton));
      expect(tapped, isTrue);
    });
  });

  group('TagChip / TagSection', () {
    testWidgets('tapping an option reports it as selected', (tester) async {
      String? selected;
      await tester.pumpWidget(_host(
        StatefulBuilder(
          builder: (context, setState) {
            return TagSection(
              label: 'Genre',
              options: const ['Pop', 'Rock', 'Jazz'],
              selected: selected,
              onSelect: (v) => setState(() => selected = v),
            );
          },
        ),
      ));

      expect(find.text('Genre'), findsOneWidget);
      await tester.tap(find.text('Rock'));
      await tester.pump();
      expect(selected, 'Rock');
    });
  });
}
