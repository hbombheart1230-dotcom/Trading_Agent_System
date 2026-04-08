[아키텍처 원칙]
앞으로 모든 설정의 선택과 권한은 Commander가 가진다.
새로운 env 토글이나 agent별 독자 설정 소유권을 추가하지 말 것.
설정이 필요하면 Commander-applied policy 또는 runtime state를 통해 주입하고,
다른 agent는 이를 소비만 하게 만들어라.
env는 가능한 한 줄이고, 설정 권한은 Commander로 집중시켜라.