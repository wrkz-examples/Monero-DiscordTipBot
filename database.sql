SET NAMES utf8;
SET time_zone = '+00:00';
SET foreign_key_checks = 0;
SET sql_mode = 'NO_AUTO_VALUE_ON_ZERO';

SET NAMES utf8mb4;

DROP TABLE IF EXISTS `notify_new_tx`;
CREATE TABLE `notify_new_tx` (
  `coin_name` varchar(32) NOT NULL,
  `owner_id` varchar(32) DEFAULT NULL,
  `owner_name` varchar(64) CHARACTER SET utf8mb4 DEFAULT NULL,
  `txid` varchar(64) NOT NULL,
  `payment_id` varchar(64) NOT NULL,
  `height` int(11) DEFAULT NULL,
  `blockhash` varchar(64) DEFAULT NULL,
  `amount` decimal(28,8) NOT NULL,
  `fee` int(11) DEFAULT NULL,
  `decimal` bigint(16) NOT NULL,
  `notified` enum('NO','YES') NOT NULL DEFAULT 'NO',
  `notified_time` decimal(16,3) DEFAULT NULL,
  `failed_notify` enum('NO','YES') DEFAULT 'NO',
  UNIQUE KEY `txid` (`txid`),
  KEY `owner_id` (`owner_id`),
  KEY `notified` (`notified`),
  KEY `payment_id` (`payment_id`),
  KEY `failed_notify` (`failed_notify`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8;


DROP TABLE IF EXISTS `xmr_external_tx`;
CREATE TABLE `xmr_external_tx` (
  `coin_name` varchar(16) NOT NULL,
  `user_id` varchar(32) NOT NULL,
  `amount` bigint(20) NOT NULL,
  `fee` bigint(16) NOT NULL,
  `decimal` bigint(16) NOT NULL,
  `to_address` varchar(128) NOT NULL,
  `type` enum('SEND','WITHDRAW') NOT NULL DEFAULT 'WITHDRAW',
  `date` int(11) NOT NULL,
  `tx_hash` varchar(64) NOT NULL,
  `tx_key` varchar(1024) NOT NULL,
  `user_server` enum('DISCORD','TELEGRAM') NOT NULL DEFAULT 'DISCORD',
  KEY `user_id` (`user_id`),
  KEY `coin_name` (`coin_name`)
) ENGINE=InnoDB DEFAULT CHARSET=ascii;


DROP TABLE IF EXISTS `xmr_get_transfers`;
CREATE TABLE `xmr_get_transfers` (
  `coin_name` varchar(16) NOT NULL,
  `in_out` varchar(16) NOT NULL,
  `txid` varchar(64) NOT NULL,
  `payment_id` varchar(64) NOT NULL,
  `height` int(11) NOT NULL,
  `timestamp` int(11) NOT NULL,
  `amount` bigint(20) NOT NULL,
  `fee` int(11) NOT NULL,
  `decimal` bigint(16) NOT NULL,
  `address` varchar(128) NOT NULL,
  `time_insert` int(11) NOT NULL,
  UNIQUE KEY `txid` (`txid`),
  KEY `payment_id` (`payment_id`),
  KEY `coin_name` (`coin_name`)
) ENGINE=InnoDB DEFAULT CHARSET=ascii;


DROP TABLE IF EXISTS `xmr_mv_tx`;
CREATE TABLE `xmr_mv_tx` (
  `coin_name` varchar(16) NOT NULL,
  `from_userid` varchar(32) NOT NULL,
  `to_userid` varchar(32) NOT NULL,
  `amount` bigint(20) NOT NULL,
  `decimal` bigint(16) NOT NULL,
  `type` enum('TIP','TIPS','TIPALL','DONATE','FREETIP') NOT NULL DEFAULT 'TIP',
  `date` int(11) NOT NULL,
  KEY `coin_name` (`coin_name`),
  KEY `from_userid` (`from_userid`),
  KEY `to_userid` (`to_userid`)
) ENGINE=InnoDB DEFAULT CHARSET=ascii;


DROP TABLE IF EXISTS `xmr_user_paymentid`;
CREATE TABLE `xmr_user_paymentid` (
  `coin_name` varchar(16) NOT NULL,
  `user_id` varchar(32) NOT NULL,
  `main_address` varchar(128) NOT NULL,
  `paymentid` varchar(64) NOT NULL,
  `int_address` varchar(128) NOT NULL,
  `paymentid_ts` int(11) NOT NULL,
  `user_wallet_address` varchar(128) DEFAULT NULL,
  `actual_balance` bigint(20) NOT NULL DEFAULT 0,
  `locked_balance` bigint(20) NOT NULL DEFAULT 0,
  `lastUpdate` int(11) NOT NULL DEFAULT 0,
  `user_server` enum('DISCORD','TELEGRAM') NOT NULL DEFAULT 'DISCORD',
  KEY `user_id` (`user_id`),
  KEY `paymentid` (`paymentid`),
  KEY `coin_name` (`coin_name`)
) ENGINE=InnoDB DEFAULT CHARSET=ascii;
